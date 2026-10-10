import threading
from typing import Dict, List, Optional
from datetime import datetime
import uuid
from app.core.state_machine import CaseStatus, validate_transition, InvalidStateTransitionError
from app.schemas.case import CaseCreate, CaseUpdate, CaseResponse
from app.schemas.audit import AuditEventType
from app.services.audit_service import audit_service


class CaseConflictError(Exception):
    """Raised when a concurrency race condition occurs during case acceptance."""
    pass


class CaseNotFoundError(Exception):
    """Raised when a requested case does not exist."""
    pass


class CaseUpdateNotAllowedError(Exception):
    """Raised when attempting to update a case that is not in DRAFT status."""
    pass


class DuplicateIdempotencyKeyError(Exception):
    """Raised when a submission with an existing idempotency key is received."""
    def __init__(self, existing_case: CaseResponse):
        self.existing_case = existing_case
        super().__init__(f"Duplicate submission with idempotencyKey '{existing_case.idempotencyKey}'.")


class CaseService:
    def __init__(self):
        self._cases: Dict[str, CaseResponse] = {}
        self._idempotency_map: Dict[str, str] = {}  # idempotency_key -> caseId
        self._lock = threading.Lock()  # Atomic lock for thread safety & simulated Firestore transactions

    def create_case(self, case_in: CaseCreate, actor_id: str, actor_role: str = "patient") -> CaseResponse:
        """
        Creates a new case in DRAFT status.
        Idempotent: If an idempotencyKey has already been processed, returns the existing case.
        """
        with self._lock:
            # Check idempotency key to prevent duplicate creation on double-click
            if case_in.idempotencyKey in self._idempotency_map:
                existing_id = self._idempotency_map[case_in.idempotencyKey]
                return self._cases[existing_id]

            case_id = f"case_{uuid.uuid4().hex[:12]}"
            now = datetime.utcnow()
            new_case = CaseResponse(
                caseId=case_id,
                patientId=case_in.patientId or actor_id,
                assignedClinicianId=None,
                requestedUrgency=case_in.requestedUrgency,
                status=CaseStatus.DRAFT,
                idempotencyKey=case_in.idempotencyKey,
                chiefComplaint=case_in.chiefComplaint,
                duration=case_in.duration,
                patientLanguage=case_in.patientLanguage,
                documentCount=0,
                doctorBriefId=None,
                consultationId=None,
                version=1,
                metadata={},
                createdAt=now,
                updatedAt=now,
            )
            self._cases[case_id] = new_case
            self._idempotency_map[case_in.idempotencyKey] = case_id

            audit_service.log_event(
                event_type=AuditEventType.CASE_CREATED,
                actor_id=actor_id,
                actor_role=actor_role,
                case_id=case_id,
                details={
                    "requestedUrgency": case_in.requestedUrgency.value,
                    "idempotencyKey": case_in.idempotencyKey,
                    "patientLanguage": case_in.patientLanguage,
                },
            )
            return new_case

    def get_case(self, case_id: str) -> CaseResponse:
        """Retrieves a single case by caseId."""
        case = self._cases.get(case_id)
        if not case:
            raise CaseNotFoundError(f"Case '{case_id}' not found.")
        return case

    def list_cases(self, patient_id: Optional[str] = None, clinician_id: Optional[str] = None) -> List[CaseResponse]:
        """Lists cases filtered optionally by patient_id or assigned clinician_id."""
        cases = list(self._cases.values())
        if patient_id:
            cases = [c for c in cases if c.patientId == patient_id]
        if clinician_id:
            cases = [c for c in cases if c.assignedClinicianId == clinician_id]
        return sorted(cases, key=lambda c: c.createdAt, reverse=True)

    def list_matching_pool(self) -> List[CaseResponse]:
        """Returns cases available in MATCHING status for clinicians to claim."""
        return [c for c in self._cases.values() if c.status == CaseStatus.MATCHING and c.assignedClinicianId is None]

    def update_case(
        self,
        case_id: str,
        update_in: CaseUpdate,
        actor_id: str,
        actor_role: str,
    ) -> CaseResponse:
        """
        Updates fields of an existing case.
        Enforces rule: Can ONLY update while case is in DRAFT status.
        Increments version and records a CASE_UPDATED audit event.
        """
        with self._lock:
            case = self.get_case(case_id)
            if case.status != CaseStatus.DRAFT:
                raise CaseUpdateNotAllowedError(
                    f"Cannot update case '{case_id}' in '{case.status.value}' status. "
                    "Cases can only be edited while in DRAFT status."
                )

            now = datetime.utcnow()
            update_data = {
                "updatedAt": now,
                "version": case.version + 1,
            }
            if update_in.chiefComplaint is not None:
                update_data["chiefComplaint"] = update_in.chiefComplaint
            if update_in.duration is not None:
                update_data["duration"] = update_in.duration
            if update_in.requestedUrgency is not None:
                update_data["requestedUrgency"] = update_in.requestedUrgency
            if update_in.patientLanguage is not None:
                update_data["patientLanguage"] = update_in.patientLanguage

            updated_case = case.model_copy(update=update_data)
            self._cases[case_id] = updated_case

            audit_service.log_event(
                event_type=AuditEventType.CASE_UPDATED,
                actor_id=actor_id,
                actor_role=actor_role,
                case_id=case_id,
                details={
                    "updatedFields": [k for k in update_data.keys() if k not in ["updatedAt", "version"]],
                    "newVersion": updated_case.version,
                },
            )
            return updated_case

    def delete_case(
        self,
        case_id: str,
        actor_id: str,
        actor_role: str,
        reason: Optional[str] = "Cancelled by user",
    ) -> CaseResponse:
        """
        Cancels / archives a case.
        If in DRAFT or any state where CANCELLED is allowed, transitions to CANCELLED.
        """
        return self.transition_status(
            case_id=case_id,
            target_status=CaseStatus.CANCELLED,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
        )

    def submit_case(
        self,
        case_id: str,
        actor_id: str,
        actor_role: str,
        idempotency_key: Optional[str] = None,
    ) -> CaseResponse:
        """
        Idempotent submission of a case:
        - If DRAFT: transitions to SUBMITTED, sets submittedAt, logs CASE_SUBMITTED.
        - If already SUBMITTED: returns existing case (idempotent, no error).
        - If any other state: raises InvalidStateTransitionError.
        """
        with self._lock:
            case = self.get_case(case_id)
            if case.status == CaseStatus.SUBMITTED:
                # Idempotent return without duplicate transition or exception
                return case

            # Must be valid transition from current to SUBMITTED
            validate_transition(case.status, CaseStatus.SUBMITTED)

            now = datetime.utcnow()
            updated_case = case.model_copy(
                update={
                    "status": CaseStatus.SUBMITTED,
                    "submittedAt": now,
                    "updatedAt": now,
                    "version": case.version + 1,
                }
            )
            self._cases[case_id] = updated_case

            audit_service.log_event(
                event_type=AuditEventType.CASE_SUBMITTED,
                actor_id=actor_id,
                actor_role=actor_role,
                case_id=case_id,
                details={
                    "from": case.status.value,
                    "to": CaseStatus.SUBMITTED.value,
                    "idempotencyKey": idempotency_key,
                },
            )
            return updated_case

    def transition_status(
        self,
        case_id: str,
        target_status: CaseStatus,
        actor_id: str,
        actor_role: str,
        reason: Optional[str] = None,
    ) -> CaseResponse:
        """
        Central State Transition Engine.
        Single source of truth for all case state changes:
        1. Validates transition legality via validate_transition().
        2. Sets appropriate milestone timestamps (submittedAt, acceptedAt, completedAt).
        3. Increments version and bumps updatedAt.
        4. Emits append-only AuditEvent for the transition.
        """
        with self._lock:
            case = self.get_case(case_id)
            validate_transition(case.status, target_status)

            now = datetime.utcnow()
            update_data = {
                "status": target_status,
                "updatedAt": now,
                "version": case.version + 1,
            }
            if target_status == CaseStatus.SUBMITTED:
                update_data["submittedAt"] = now
            elif target_status == CaseStatus.ACCEPTED:
                update_data["acceptedAt"] = now
            elif target_status == CaseStatus.COMPLETED:
                update_data["completedAt"] = now

            updated_case = case.model_copy(update=update_data)
            self._cases[case_id] = updated_case

            # Map status transitions to explicit AuditEventTypes
            event_type_map = {
                CaseStatus.SUBMITTED: AuditEventType.CASE_SUBMITTED,
                CaseStatus.MATCHING: AuditEventType.CASE_MATCHING_ENQUEUED,
                CaseStatus.ACCEPTED: AuditEventType.CASE_ACCEPTED,
                CaseStatus.IN_CONSULTATION: AuditEventType.CASE_IN_CONSULTATION,
                CaseStatus.COMPLETED: AuditEventType.CASE_COMPLETED,
                CaseStatus.CANCELLED: AuditEventType.CASE_CANCELLED,
                CaseStatus.ESCALATED: AuditEventType.CASE_ESCALATED,
                CaseStatus.FAILED: AuditEventType.CASE_FAILED,
                CaseStatus.NO_CLINICIAN_AVAILABLE: AuditEventType.CASE_NO_CLINICIAN,
            }
            event_type = event_type_map.get(target_status, AuditEventType.CASE_UPDATED)

            audit_service.log_event(
                event_type=event_type,
                actor_id=actor_id,
                actor_role=actor_role,
                case_id=case_id,
                details={
                    "from": case.status.value,
                    "to": target_status.value,
                    "reason": reason,
                    "version": updated_case.version,
                },
            )
            return updated_case

    def accept_case_atomic(self, case_id: str, clinician_id: str) -> CaseResponse:
        """
        Concurrency-safe case acceptance.
        Simulates Firestore atomic transaction:
        Re-reads case, checks status == MATCHING and unassigned, sets assignedClinicianId and ACCEPTED.
        Any concurrent attempt raises CaseConflictError (HTTP 409).
        """
        with self._lock:
            case = self.get_case(case_id)
            if case.status != CaseStatus.MATCHING or case.assignedClinicianId is not None:
                audit_service.log_event(
                    event_type=AuditEventType.CONFLICT_DETECTED,
                    actor_id=clinician_id,
                    actor_role="clinician",
                    case_id=case_id,
                    details={
                        "attemptedClinicianId": clinician_id,
                        "currentStatus": case.status.value,
                        "alreadyAssignedTo": case.assignedClinicianId,
                    },
                )
                raise CaseConflictError(
                    f"Case '{case_id}' cannot be accepted. "
                    f"Status is '{case.status.value}' and assignedClinicianId is '{case.assignedClinicianId}'."
                )

            now = datetime.utcnow()
            updated_case = case.model_copy(
                update={
                    "status": CaseStatus.ACCEPTED,
                    "assignedClinicianId": clinician_id,
                    "acceptedAt": now,
                    "updatedAt": now,
                    "version": case.version + 1,
                }
            )
            self._cases[case_id] = updated_case

            audit_service.log_event(
                event_type=AuditEventType.CASE_ACCEPTED,
                actor_id=clinician_id,
                actor_role="clinician",
                case_id=case_id,
                details={"assignedClinicianId": clinician_id, "version": updated_case.version},
            )
            return updated_case

    def increment_document_count(self, case_id: str) -> CaseResponse:
        """Atomically increments the document count for a case."""
        with self._lock:
            case = self.get_case(case_id)
            updated_case = case.model_copy(
                update={
                    "documentCount": case.documentCount + 1,
                    "updatedAt": datetime.utcnow(),
                }
            )
            self._cases[case_id] = updated_case
            return updated_case


case_service = CaseService()
