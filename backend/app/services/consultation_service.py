import logging
from datetime import datetime
from typing import Optional, Tuple
from fastapi import HTTPException, status

from app.core.firestore_client import get_firestore_client
from app.core.state_machine import CaseStatus, InvalidStateTransitionError
from app.models.firestore_models import (
    consultation_to_firestore_dict,
    consultation_from_firestore_dict,
    follow_up_to_firestore_dict,
    follow_up_from_firestore_dict,
)
from app.schemas.case import CaseResponse
from app.schemas.consultation import (
    ConsultationCreate,
    ConsultationResponse,
    ConsultationType,
    FollowUpCreate,
    FollowUpResponse,
    FollowUpStatus,
)
from app.services.case_service import case_service

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

    def complete_case_and_followup(
        self,
        case_id: str,
        clinician_id: str,
        data: FollowUpCreate,
        actor_id: str,
        actor_role: str,
    ) -> Tuple[CaseResponse, FollowUpResponse]:
        """
        Finalizes case coordination and schedules patient follow-up.
        1. Verifies assigned clinician permissions.
        2. Transitions case IN_CONSULTATION -> COMPLETED.
        3. Persists follow-up record in Firestore collection 'follow_ups'.
        4. Releases clinician availability from 'busy' back to 'available' with currentCaseId=None.
        5. Emits CASE_COMPLETED audit event.
        """
        case = case_service.get_case(case_id)

        # RBAC: Only assigned clinician can complete the case
        if case.assignedClinicianId != clinician_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Clinician '{clinician_id}' is not assigned to case '{case_id}' (assigned: '{case.assignedClinicianId}').",
            )

        if case.status == CaseStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Case '{case_id}' is already in terminal COMPLETED status.",
            )

        if case.status not in (CaseStatus.IN_CONSULTATION, CaseStatus.ACCEPTED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot complete case '{case_id}' with status '{case.status.value}'. Must be IN_CONSULTATION or ACCEPTED.",
            )

        now = datetime.utcnow()
        follow_up_id = f"followup_{case_id}"
        follow_up = FollowUpResponse(
            followUpId=follow_up_id,
            caseId=case_id,
            patientId=case.patientId,
            clinicianId=clinician_id,
            required=data.required,
            recommendedDate=data.recommendedDate,
            status=FollowUpStatus.SCHEDULED,
            instructions=data.instructions,
            createdAt=now,
        )

        # Persist follow-up record
        self.db.collection("follow_ups").document(case_id).set(
            follow_up_to_firestore_dict(follow_up)
        )

        # If still in ACCEPTED, step through IN_CONSULTATION first
        if case.status == CaseStatus.ACCEPTED:
            case = case_service.transition_status(
                case_id=case_id,
                target_status=CaseStatus.IN_CONSULTATION,
                actor_id=actor_id,
                actor_role=actor_role,
                reason="Automatic advancement through IN_CONSULTATION on finalization",
            )

        # Transition case to terminal COMPLETED status
        completed_case = case_service.transition_status(
            case_id=case_id,
            target_status=CaseStatus.COMPLETED,
            actor_id=actor_id,
            actor_role=actor_role,
            reason="Clinician finalized consultation and scheduled follow-up directives",
            extra_details={
                "followUpId": follow_up_id,
                "followUpRequired": follow_up.required,
                "recommendedDate": follow_up.recommendedDate,
            },
        )

        # Release clinician availability back to available
        try:
            clinician_ref = self.db.collection("clinicians").document(clinician_id)
            clin_snap = clinician_ref.get()
            if clin_snap.exists:
                clinician_ref.update({
                    "availability": "available",
                    "currentCaseId": None,
                    "updatedAt": now.isoformat(),
                })
                logger.info(f"Released clinician '{clinician_id}' availability to 'available'")
        except Exception as e:
            logger.warning(f"Failed to reset clinician '{clinician_id}' availability: {e}")

        logger.info(f"Completed case '{case_id}' with follow-up '{follow_up_id}' by clinician '{clinician_id}'")
        return completed_case, follow_up

    def get_follow_up(self, case_id: str) -> Optional[FollowUpResponse]:
        """Retrieves follow-up record for a given case."""
        snapshot = self.db.collection("follow_ups").document(case_id).get()
        if not snapshot.exists:
            return None
        return follow_up_from_firestore_dict(case_id, snapshot.to_dict())


consultation_service = ConsultationService()
