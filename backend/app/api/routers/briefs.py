from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional

from app.core.auth import (
    get_current_user,
    require_verified_clinician,
    AuthenticatedUser,
)
from app.schemas.doctor_brief import (
    DoctorBrief,
    DoctorBriefGenerateRequest,
    DoctorBriefEditRequest,
    DoctorBriefPatientApproveRequest,
    DoctorBriefClinicianReviewRequest,
)
from app.services.brief_service import (
    brief_service,
    BriefGenerationError,
    BriefNotFoundError,
    BriefEditConflictError,
    BriefUpdateNotAllowedError,
    BriefRateLimitError,
    BriefAccessForbiddenError,
)
from app.services.case_service import CaseNotFoundError

router = APIRouter(prefix="/cases", tags=["doctor-brief"])


@router.post("/{case_id}/brief/generate", response_model=DoctorBrief, status_code=status.HTTP_200_OK)
def generate_doctor_brief(
    case_id: str,
    req: Optional[DoctorBriefGenerateRequest] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Generates or regenerates an AI Doctor Brief using Gemini.
    - Restricted to case owner (or admin) while case is in DRAFT status.
    - If regenerating over an edited brief, confirmRegenerate=true is required.
    - Per-case rate limits enforced.
    - Always returns a valid brief (or blank skeleton on AI failure) without crashing.
    """
    confirm_regenerate = req.confirmRegenerate if req else False
    try:
        brief, _ = brief_service.generate_brief(
            case_id=case_id,
            actor_id=current_user.uid,
            actor_role=current_user.role,
            confirm_regenerate=confirm_regenerate,
        )
        return brief
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BriefAccessForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except BriefRateLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except (BriefGenerationError, BriefEditConflictError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{case_id}/brief", response_model=DoctorBrief)
def get_doctor_brief(
    case_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retrieves the Doctor Brief for a case with strict RBAC rules:
    - Patient owner: always allowed.
    - Admin: always allowed.
    - Clinician: allowed ONLY if assigned to the case AND case is in ACCEPTED, IN_CONSULTATION, or COMPLETED.
    - All other users receive HTTP 403 Forbidden.
    """
    try:
        return brief_service.get_brief(
            case_id=case_id,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BriefNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BriefAccessForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.put("/{case_id}/brief", response_model=DoctorBrief)
def edit_doctor_brief(
    case_id: str,
    edit_in: DoctorBriefEditRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Applies human edits to an existing Doctor Brief.
    - Patients can only edit while case is in DRAFT status (locked after SUBMITTED).
    - Clinicians can edit if assigned when case is ACCEPTED, IN_CONSULTATION, or COMPLETED.
    - Transitions briefStatus to EDITED, increments version counter, and stores snapshot in previousVersions.
    """
    try:
        return brief_service.edit_brief(
            case_id=case_id,
            edit_in=edit_in,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BriefNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (BriefAccessForbiddenError, BriefUpdateNotAllowedError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{case_id}/brief/approve", response_model=DoctorBrief)
def approve_doctor_brief_patient(
    case_id: str,
    req: Optional[DoctorBriefPatientApproveRequest] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Patient approval gate for Doctor Brief.
    - Restricted to case owner.
    - Transitions briefStatus to PATIENT_APPROVED.
    """
    try:
        return brief_service.approve_brief_patient(
            case_id=case_id,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BriefNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BriefAccessForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{case_id}/brief/review", response_model=DoctorBrief)
def review_doctor_brief_clinician(
    case_id: str,
    req: Optional[DoctorBriefClinicianReviewRequest] = None,
    current_user: AuthenticatedUser = Depends(require_verified_clinician),
):
    """
    Clinician review gate for Doctor Brief.
    - Restricted to assigned verified clinician.
    - Only allowed when case is ACCEPTED, IN_CONSULTATION, or COMPLETED.
    - Transitions briefStatus to CLINICIAN_REVIEWED.
    """
    try:
        return brief_service.review_brief_clinician(
            case_id=case_id,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BriefNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BriefAccessForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
