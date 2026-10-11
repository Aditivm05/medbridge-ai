import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import get_current_user, require_verified_clinician, check_case_ownership, AuthenticatedUser
from app.schemas.case import CaseResponse
from app.schemas.consultation import (
    ConsultationCreate,
    ConsultationResponse,
    FollowUpCreate,
    FollowUpResponse,
)
from app.services.case_service import case_service, CaseNotFoundError
from app.services.consultation_service import consultation_service

logger = logging.getLogger("medbridge.api.consultations")
router = APIRouter(prefix="/cases", tags=["consultations"])


class CaseCompletionResponse(BaseModel):
    case: CaseResponse
    followUp: FollowUpResponse


@router.post("/{case_id}/consultation", response_model=ConsultationResponse)
def record_consultation(
    case_id: str,
    data: ConsultationCreate,
    current_user: AuthenticatedUser = Depends(require_verified_clinician),
):
    """
    Assigned verified clinician records clinical assessment observations and supportive care advice.
    - Transitions case status from ACCEPTED to IN_CONSULTATION.
    - Persists consultation record in Firestore.
    - Emits CASE_IN_CONSULTATION audit event.
    """
    try:
        return consultation_service.save_consultation(
            case_id=case_id,
            clinician_id=current_user.uid,
            data=data,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{case_id}/consultation", response_model=ConsultationResponse)
def get_consultation(
    case_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retrieves the recorded consultation for a case.
    - Accessible to the patient owner, assigned clinician, or admin.
    - Other users receive HTTP 403 Forbidden.
    """
    try:
        case = case_service.get_case(case_id)
        if current_user.role == "patient":
            check_case_ownership(case.patientId, current_user)
        elif current_user.role == "clinician":
            if case.assignedClinicianId != current_user.uid:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: Clinician '{current_user.uid}' is not assigned to case '{case_id}'.",
                )

        consultation = consultation_service.get_consultation(case_id)
        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No consultation recorded yet for case '{case_id}'.",
            )
        return consultation
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{case_id}/complete", response_model=CaseCompletionResponse)
@router.post("/{case_id}/follow-up", response_model=CaseCompletionResponse)
def complete_case_and_followup(
    case_id: str,
    data: FollowUpCreate,
    current_user: AuthenticatedUser = Depends(require_verified_clinician),
):
    """
    Assigned verified clinician schedules patient follow-up and finalizes the coordination case.
    - Transitions case status to terminal COMPLETED.
    - Persists follow-up record with required/recommendedDate/instructions.
    - Releases clinician availability to 'available'.
    - Emits CASE_COMPLETED audit event.
    """
    try:
        updated_case, follow_up = consultation_service.complete_case_and_followup(
            case_id=case_id,
            clinician_id=current_user.uid,
            data=data,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
        return CaseCompletionResponse(case=updated_case, followUp=follow_up)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{case_id}/follow-up", response_model=FollowUpResponse)
def get_follow_up(
    case_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retrieves the scheduled follow-up record for a case.
    - Accessible to the patient owner, assigned clinician, or admin.
    - Other users receive HTTP 403 Forbidden.
    """
    try:
        case = case_service.get_case(case_id)
        if current_user.role == "patient":
            check_case_ownership(case.patientId, current_user)
        elif current_user.role == "clinician":
            if case.assignedClinicianId != current_user.uid:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: Clinician '{current_user.uid}' is not assigned to case '{case_id}'.",
                )

        follow_up = consultation_service.get_follow_up(case_id)
        if not follow_up:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No follow-up record found for case '{case_id}'.",
            )
        return follow_up
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
