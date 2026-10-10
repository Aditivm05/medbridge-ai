import threading
from typing import Dict, List, Optional
from datetime import datetime
import uuid

from app.core.state_machine import CaseStatus, validate_transition, InvalidStateTransitionError
from app.schemas.case import CaseCreate, CaseUpdate, CaseResponse
from app.schemas.audit import AuditEventType
from app.services.audit_service import audit_service
from app.core.firestore_client import get_firestore_client, firestore_transactional
from app.models.firestore_models import case_to_firestore_dict, case_from_firestore_dict


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
    def __init__(self, db=None):
        self._db = db
        self._lock = threading.Lock()

    @property
    def db(self):
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    # Compatibility adapter for legacy test references
    @property
    def _cases(self):
        parent = self
        class _CasesAdapter:
            def __getitem__(self, case_id: str):
                return parent.get_case(case_id)

            def __setitem__(self, case_id: str, case: CaseResponse):
                data = case_to_firestore_dict(case)
                parent.db.collection("cases").document(case_id).set(data)

            def get(self, case_id: str, default=None):
                try:
                    return parent.get_case(case_id)
                except CaseNotFoundError:
                    return default

            def values(self):
                return parent.list_cases()

            def __contains__(self, case_id: str):
                snap = parent.db.collection("cases").document(case_id).get()
                return snap.exists

        return _CasesAdapter()

    @property
    def _idempotency_map(self):
        parent = self
        class _IdemAdapter:
            def __getitem__(self, key: str):
                snap = parent.db.collection("idempotency_keys").document(key).get()
                if not snap.exists:
                    raise KeyError(key)
                return snap.to_dict().get("caseId")

            def __setitem__(self, key: str, case_id: str):
                parent.db.collection("idempotency_keys").document(key).set(
                    {"caseId": case_id, "createdAt": datetime.utcnow().isoformat()}
                )

            def __contains__(self, key: str):
                snap = parent.db.collection("idempotency_keys").document(key).get()
                return snap.exists

            def get(self, key: str, default=None):
                snap = parent.db.collection("idempotency_keys").document(key).get()
                if not snap.exists:
                    return default
                return snap.to_dict().get("caseId")

        return _IdemAdapter()

    def create_case(self, case_in: CaseCreate, actor_id: str, actor_role: str = "patient") -> CaseResponse:
        """
        Creates a new case in DRAFT status.
        Idempotent: Idempotency keys persist in Firestore under 'idempotency_keys' collection.
        If an idempotencyKey has already been processed, returns the existing case.
        """
        with self._lock:
            # 1. Check persistent idempotency key in Firestore
            idem_ref = self.db.collection("idempotency_keys").document(case_in.idempotencyKey)
            idem_snap = idem_ref.get()
            if idem_snap.exists:
                existing_case_id = idem_snap.to_dict().get("caseId")
                if existing_case_id:
                    try:
                        return self.get_case(existing_case_id)
                    except CaseNotFoundError:
                        pass

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

            # Persist Case & Idempotency Key to Firestore
            self.db.collection("cases").document(case_id).set(case_to_firestore_dict(new_case))
            idem_ref.set({
                "caseId": case_id,
                "createdAt": now.isoformat(),
                "patientId": new_case.patientId,
            })

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
        """Retrieves a single case from Firestore."""
        doc_snap = self.db.collection("cases").document(case_id).get()
        if not doc_snap.exists:
            raise CaseNotFoundError(f"Case '{case_id}' not found.")
        return case_from_firestore_dict(case_id, doc_snap.to_dict())

    def list_cases(self, patient_id: Optional[str] = None, clinician_id: Optional[str] = None) -> List[CaseResponse]:
        """Lists cases from Firestore, filtered optionally by patient_id or assigned clinician_id."""
        query = self.db.collection("cases")
        if patient_id:
            query = query.where("patientId", "==", patient_id)
        if clinician_id:
            query = query.where("assignedClinicianId", "==", clinician_id)

        snapshots = query.stream()
        cases = [case_from_firestore_dict(s.id, s.to_dict()) for s in snapshots]
        return sorted(cases, key=lambda c: c.createdAt, reverse=True)

    def list_matching_pool(self) -> List[CaseResponse]:
        """Returns cases available in MATCHING status for clinicians to claim."""
        query = self.db.collection("cases").where("status", "==", CaseStatus.MATCHING.value)
        snapshots = query.stream()
        cases = [case_from_firestore_dict(s.id, s.to_dict()) for s in snapshots]
        return [c for c in cases if c.assignedClinicianId is None]

    def update_case(
        self,
        case_id: str,
        update_in: CaseUpdate,
        actor_id: str,
        actor_role: str,
    ) -> CaseResponse:
        """
        Updates fields of an existing case in Firestore.
        Enforces rule: Can ONLY update while case is in DRAFT status.
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
            if update_in.metadata is not None:
                current_meta = dict(case.metadata or {})
                current_meta.update(update_in.metadata)
                update_data["metadata"] = current_meta

            updated_case = case.model_copy(update=update_data)
            self.db.collection("cases").document(case_id).set(case_to_firestore_dict(updated_case))

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
        Idempotent submission of a case in Firestore:
        - If DRAFT: transitions to SUBMITTED, sets submittedAt, logs CASE_SUBMITTED.
        - If already SUBMITTED: returns existing case (idempotent, no error).
        - If any other state: raises InvalidStateTransitionError.
        """
        with self._lock:
            case = self.get_case(case_id)
            if case.status == CaseStatus.SUBMITTED:
                return case

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
            self.db.collection("cases").document(case_id).set(case_to_firestore_dict(updated_case))

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
        Central State Transition Engine persisting to Firestore.
        1. Validates transition legality via validate_transition().
        2. Sets milestone timestamps (submittedAt, acceptedAt, completedAt).
        3. Increments version and bumps updatedAt.
        4. Emits append-only AuditEvent.
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
            self.db.collection("cases").document(case_id).set(case_to_firestore_dict(updated_case))

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
        Concurrency-safe case acceptance using a real Firestore transaction:
        Re-reads case inside the transaction, checks status == MATCHING and unassigned,
        then sets clinician and ACCEPTED.
        Any concurrent race collision raises CaseConflictError (HTTP 409).
        """
        @firestore_transactional(self.db)
        def _tx_accept(tx):
            case_ref = self.db.collection("cases").document(case_id)
            snapshot = case_ref.get(transaction=tx)
            if not snapshot.exists:
                raise CaseNotFoundError(f"Case '{case_id}' not found.")
            data = snapshot.to_dict()
            current_status = data.get("status")
            assigned = data.get("assignedClinicianId")

            if current_status != CaseStatus.MATCHING.value or assigned is not None:
                audit_service.log_event(
                    event_type=AuditEventType.CONFLICT_DETECTED,
                    actor_id=clinician_id,
                    actor_role="clinician",
                    case_id=case_id,
                    details={
                        "attemptedClinicianId": clinician_id,
                        "currentStatus": current_status,
                        "alreadyAssignedTo": assigned,
                    },
                )
                raise CaseConflictError(
                    f"Case '{case_id}' cannot be accepted. "
                    f"Status is '{current_status}' and assignedClinicianId is '{assigned}'."
                )

            now = datetime.utcnow()
            new_version = data.get("version", 1) + 1
            updates = {
                "status": CaseStatus.ACCEPTED.value,
                "assignedClinicianId": clinician_id,
                "acceptedAt": now.isoformat(),
                "updatedAt": now.isoformat(),
                "version": new_version,
            }
            tx.update(case_ref, updates)
            merged = dict(data, **updates)
            return case_from_firestore_dict(case_id, merged)

        updated_case = _tx_accept()

        audit_service.log_event(
            event_type=AuditEventType.CASE_ACCEPTED,
            actor_id=clinician_id,
            actor_role="clinician",
            case_id=case_id,
            details={"assignedClinicianId": clinician_id, "version": updated_case.version},
        )
        return updated_case

    def increment_document_count(self, case_id: str) -> CaseResponse:
        """Atomically increments the document count on the case in Firestore."""
        with self._lock:
            case = self.get_case(case_id)
            updated_case = case.model_copy(
                update={
                    "documentCount": case.documentCount + 1,
                    "updatedAt": datetime.utcnow(),
                }
            )
            self.db.collection("cases").document(case_id).set(case_to_firestore_dict(updated_case))
            return updated_case


case_service = CaseService()
