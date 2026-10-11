import logging
from datetime import datetime
from typing import Optional, Tuple, List
from fastapi import HTTPException, status

from app.core.firestore_client import get_firestore_client, firestore_transactional
from app.core.state_machine import CaseStatus, InvalidStateTransitionError
from app.models.firestore_models import (
    consultation_to_firestore_dict,
    consultation_from_firestore_dict,
    follow_up_to_firestore_dict,
    follow_up_from_firestore_dict,
    case_to_firestore_dict,
    case_from_firestore_dict,
    audit_event_to_firestore_dict,
)
from app.schemas.case import CaseResponse
from app.schemas.audit import AuditEventType, AuditEventResponse
from app.schemas.consultation import (
    ConsultationCreate,
    ConsultationResponse,
    ConsultationType,
    FollowUpCreate,
    FollowUpResponse,
    FollowUpStatus,
)
from app.services.case_service import case_service, CaseNotFoundError
from app.services.audit_service import audit_service

logger = logging.getLogger("medbridge.consultation_service")


class ConsultationService:
    def __init__(self):
        self.db = get_firestore_client()

    def save_consultation(
        self,
        case_id: str,
        clinician_id: str,
        data: ConsultationCreate,
        actor_id: str,
        actor_role: str,
    ) -> ConsultationResponse:
        """
        Records consultation notes and provisional care advice by the assigned clinician.
        Transitions case status from ACCEPTED -> IN_CONSULTATION if currently ACCEPTED.
        Persists consultation record in Firestore collection 'consultations'.
        """
        case = case_service.get_case(case_id)

        # RBAC: Only assigned clinician can record consultation notes
        if case.assignedClinicianId != clinician_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Clinician '{clinician_id}' is not assigned to case '{case_id}' (assigned: '{case.assignedClinicianId}').",
            )

        # Status check
        if case.status not in (CaseStatus.ACCEPTED, CaseStatus.IN_CONSULTATION):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record consultation on case '{case_id}' in status '{case.status.value}'. Requires ACCEPTED or IN_CONSULTATION.",
            )

        # Transition status to IN_CONSULTATION if currently ACCEPTED
        if case.status == CaseStatus.ACCEPTED:
            case = case_service.transition_status(
                case_id=case_id,
                target_status=CaseStatus.IN_CONSULTATION,
                actor_id=actor_id,
                actor_role=actor_role,
                reason="Clinician started consultation assessment and recorded observations",
            )

        consultation_id = f"consult_{case_id}"
        now = datetime.utcnow()
        consultation = ConsultationResponse(
            consultationId=consultation_id,
            caseId=case_id,
            clinicianId=clinician_id,
            patientId=case.patientId,
            consultationType=ConsultationType.TEXT_BASED_SIMULATED,
            isSimulated=True,
            clinicianNotes=data.clinicianNotes,
            provisionalCareAdvice=data.provisionalCareAdvice,
            startedAt=case.acceptedAt or now,
            endedAt=now,
        )

        # Persist consultation record
        self.db.collection("consultations").document(case_id).set(
            consultation_to_firestore_dict(consultation)
        )

        # Link consultationId on case
        try:
            self.db.collection("cases").document(case_id).update({
                "consultationId": consultation_id,
                "updatedAt": now.isoformat(),
            })
        except Exception as e:
            logger.warning(f"Failed to update consultationId on case '{case_id}': {e}")

        logger.info(f"Recorded consultation '{consultation_id}' for case '{case_id}' by clinician '{clinician_id}'")
        return consultation

    def get_consultation(self, case_id: str) -> Optional[ConsultationResponse]:
        """Retrieves consultation record for a given case."""
        snapshot = self.db.collection("consultations").document(case_id).get()
        if not snapshot.exists:
            return None
        return consultation_from_firestore_dict(case_id, snapshot.to_dict())

    def _get_other_active_cases(self, clinician_id: str, current_case_id: str) -> List[str]:
        """Returns list of other active case IDs (ACCEPTED or IN_CONSULTATION) assigned to clinician."""
        if not clinician_id:
            return []
        other_active: List[str] = []
        try:
            query = self.db.collection("cases").where("assignedClinicianId", "==", clinician_id)
            for snap in query.stream():
                if snap.id != current_case_id:
                    data = snap.to_dict() or {}
                    st = data.get("status")
                    if st in (CaseStatus.ACCEPTED.value, CaseStatus.IN_CONSULTATION.value):
                        other_active.append(snap.id)
        except Exception as e:
            logger.warning(f"Error checking other active cases for clinician '{clinician_id}': {e}")
        return other_active

    def _clinician_has_other_active_cases(self, clinician_id: str, current_case_id: str) -> bool:
        """
        Queries all cases assigned to clinician_id and checks whether there are other active
        cases (in ACCEPTED or IN_CONSULTATION status) besides current_case_id.
        """
        return len(self._get_other_active_cases(clinician_id, current_case_id)) > 0

    def complete_case_and_followup(
        self,
        case_id: str,
        clinician_id: str,
        data: FollowUpCreate,
        actor_id: str,
        actor_role: str,
    ) -> Tuple[CaseResponse, FollowUpResponse]:
        """
        Atomically finalizes case coordination and schedules patient follow-up using a Firestore transaction.
        Invariants enforced:
        1. Only assigned verified clinician or authorized admin can complete the case.
        2. Atomic transaction: case transition to COMPLETED, follow-up persistence, and clinician availability update occur in a single atomic transaction.
        3. All reads occur before all writes inside the transaction.
        4. Clinician availability is released to 'available' with currentCaseId=None ONLY IF the clinician has no other active assigned cases.
        5. CASE_COMPLETED audit event is recorded strictly after successful transaction commit.
        6. Repeated completion attempts on an already-completed case fail deterministically with HTTP 400.
        """
        case_ref = self.db.collection("cases").document(case_id)
        followup_ref = self.db.collection("follow_ups").document(case_id)

        # 1. Pre-transaction check: if case is currently in ACCEPTED, advance to IN_CONSULTATION
        # to respect legal state machine progression before terminal completion.
        initial_snap = case_ref.get()
        if not initial_snap.exists:
            raise CaseNotFoundError(f"Case '{case_id}' not found.")
        initial_data = initial_snap.to_dict() or {}
        assigned = initial_data.get("assignedClinicianId")

        if actor_role != "admin":
            if actor_role != "clinician":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: Clinician or admin role required. Got '{actor_role}'.",
                )
            if assigned != clinician_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: Clinician '{clinician_id}' is not assigned to case '{case_id}' (assigned: '{assigned}').",
                )

        if initial_data.get("status") == CaseStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Case '{case_id}' is already in terminal COMPLETED status.",
            )

        if initial_data.get("status") == CaseStatus.ACCEPTED.value:
            case_service.transition_status(
                case_id=case_id,
                target_status=CaseStatus.IN_CONSULTATION,
                actor_id=actor_id,
                actor_role=actor_role,
                reason="Automatic advancement through IN_CONSULTATION on finalization",
            )

        # 2. Check if the clinician has other active cases prior to/during transaction
        effective_clinician_id = assigned or clinician_id
        has_other_active = self._clinician_has_other_active_cases(effective_clinician_id, case_id)

        # 3. Define and run the atomic transaction
        @firestore_transactional(self.db)
        def _tx_complete(tx):
            # All reads must precede all writes in Firestore transactions
            c_snap = case_ref.get(transaction=tx)
            if not c_snap.exists:
                raise CaseNotFoundError(f"Case '{case_id}' not found.")
            c_data = c_snap.to_dict() or {}
            c_status = c_data.get("status")
            c_assigned = c_data.get("assignedClinicianId")

            # Invariant check: role and assignment
            if actor_role != "admin":
                if c_assigned != clinician_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Forbidden: Clinician '{clinician_id}' is not assigned to case '{case_id}' (assigned: '{c_assigned}').",
                    )

            # Invariant check: terminal and valid status
            if c_status == CaseStatus.COMPLETED.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Case '{case_id}' is already in terminal COMPLETED status.",
                )
            if c_status not in (CaseStatus.IN_CONSULTATION.value, CaseStatus.ACCEPTED.value):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot complete case '{case_id}' with status '{c_status}'. Must be IN_CONSULTATION or ACCEPTED.",
                )

            # Read clinician document if assigned
            clin_doc_ref = None
            clin_snap = None
            if effective_clinician_id:
                clin_doc_ref = self.db.collection("clinicians").document(effective_clinician_id)
                clin_snap = clin_doc_ref.get(transaction=tx)

            # Read existing follow-up document (if any)
            followup_ref.get(transaction=tx)

            # All reads complete. Now stage atomic writes:
            now = datetime.utcnow()
            f_id = f"followup_{case_id}"
            f_model = FollowUpResponse(
                followUpId=f_id,
                caseId=case_id,
                patientId=c_data.get("patientId"),
                clinicianId=effective_clinician_id,
                required=data.required,
                recommendedDate=data.recommendedDate,
                status=FollowUpStatus.SCHEDULED,
                instructions=data.instructions,
                createdAt=now,
            )
            # Staged Write 1: Persist follow-up record
            tx.set(followup_ref, follow_up_to_firestore_dict(f_model))

            # Staged Write 2: Transition case to terminal COMPLETED
            new_ver = c_data.get("version", 1) + 1
            case_updates = {
                "status": CaseStatus.COMPLETED.value,
                "completedAt": now.isoformat(),
                "updatedAt": now.isoformat(),
                "version": new_ver,
            }
            tx.update(case_ref, case_updates)

            # Staged Write 3: Release clinician availability ONLY if currentCaseId matches this case (or None) and no other active cases
            clinician_released = False
            if clin_snap and clin_snap.exists:
                clin_data = clin_snap.to_dict() or {}
                c_current_case = clin_data.get("currentCaseId")
                # Dynamically re-evaluate other active cases inside the transaction on every attempt/retry
                other_active = self._get_other_active_cases(effective_clinician_id, case_id)
                has_other_active = len(other_active) > 0

                # Invariant: Never clear currentCaseId if it points to a different case!
                if c_current_case == case_id or c_current_case is None:
                    if not has_other_active:
                        clinician_released = True
                        tx.update(clin_doc_ref, {
                            "availability": "available",
                            "currentCaseId": None,
                            "updatedAt": now.isoformat(),
                        })
                    else:
                        # Clinician has other active cases. Retain busy status.
                        # Transition currentCaseId to the next active case.
                        clinician_released = False
                        tx.update(clin_doc_ref, {
                            "availability": "busy",
                            "currentCaseId": other_active[0],
                            "updatedAt": now.isoformat(),
                        })
                else:
                    # c_current_case points to a different case (e.g. concurrent assignment/acceptance of Case B).
                    # Under NO circumstances should this completion clear or overwrite c_current_case.
                    clinician_released = False

            # Staged Write 4: Atomically persist CASE_COMPLETED audit event in the same transaction
            audit_event_id = f"audit_completed_{case_id}"
            audit_doc_ref = self.db.collection("audit_events").document(audit_event_id)
            completion_event = AuditEventResponse(
                eventId=audit_event_id,
                caseId=case_id,
                actorId=actor_id,
                actorRole=actor_role,
                eventType=AuditEventType.CASE_COMPLETED,
                ipAddress=None,
                userAgent=None,
                details={
                    "from": c_status,
                    "to": CaseStatus.COMPLETED.value,
                    "reason": "Clinician finalized consultation and scheduled follow-up directives",
                    "version": new_ver,
                    "followUpId": f_id,
                    "followUpRequired": f_model.required,
                    "recommendedDate": f_model.recommendedDate,
                    "clinicianReleased": clinician_released,
                },
                timestamp=now,
            )
            tx.set(audit_doc_ref, audit_event_to_firestore_dict(completion_event))

            merged_case_data = dict(c_data, **case_updates)
            final_case = case_from_firestore_dict(case_id, merged_case_data)
            return final_case, f_model, completion_event, clinician_released

        try:
            completed_case, follow_up, completion_event, released = _tx_complete()
        except HTTPException:
            raise
        except CaseNotFoundError:
            raise
        except Exception as e:
            err_str = str(e).lower()
            if "conflict" in err_str or "aborted" in err_str or "precondition" in err_str:
                audit_service.log_event(
                    event_type=AuditEventType.CONFLICT_DETECTED,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    case_id=case_id,
                    details={"attemptedAction": "complete_case", "error": str(e)},
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Concurrency collision completing case '{case_id}': {e}",
                )
            raise

        # 4. Register the transactionally committed audit event into local cache
        audit_service.record_committed_event(completion_event)

        logger.info(
            f"Atomically completed case '{case_id}' with follow-up '{follow_up.followUpId}' "
            f"(clinician released: {released}, audit event: '{completion_event.eventId}')"
        )
        return completed_case, follow_up

    def get_follow_up(self, case_id: str) -> Optional[FollowUpResponse]:
        """Retrieves follow-up record for a given case."""
        snapshot = self.db.collection("follow_ups").document(case_id).get()
        if not snapshot.exists:
            return None
        return follow_up_from_firestore_dict(case_id, snapshot.to_dict())


consultation_service = ConsultationService()
