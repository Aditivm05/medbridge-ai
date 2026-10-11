from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from app.schemas.case import (
    CaseCreate,
    CaseUpdate,
    CaseResponse,
    CaseSubmitRequest,
    StateTransitionRequest,
    CaseAcceptRequest,
)
from app.core.state_machine import CaseStatus, InvalidStateTransitionError
from app.schemas.clinician import ClinicianMatchResponse, CaseDeclineRequest
from app.services.clinician_service import clinician_service
from app.services.case_service import (
    case_service,
    CaseConflictError,
    CaseNotFoundError,
    CaseUpdateNotAllowedError,
)
from app.core.auth import (
    get_current_user,
    require_role,
    require_verified_clinician,
    check_case_ownership,
    AuthenticatedUser,
)

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    case_in: CaseCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Creates a new case draft.
    - Idempotent: If an idempotencyKey was already submitted, returns existing case.
    - Patients automatically create cases under their authenticated uid.
    """
    effective_patient_id = current_user.uid if current_user.role == "patient" else (case_in.patientId or current_user.uid)
    adjusted_case_in = case_in.model_copy(update={"patientId": effective_patient_id})

    try:
        created = case_service.create_case(
            adjusted_case_in,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
        return created
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[CaseResponse])
def list_cases(
    patientId: Optional[str] = None,
    clinicianId: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Lists cases based on role and ownership:
    - Patients ONLY see their own cases.
    - Clinicians see cases assigned to them.
    - Admins see all cases or query filters.
    """
    if current_user.role == "patient":
        return case_service.list_cases(patient_id=current_user.uid)

    if current_user.role == "clinician":
        return case_service.list_cases(clinician_id=current_user.uid)

    return case_service.list_cases(patient_id=patientId, clinician_id=clinicianId)


@router.get("/matching-pool", response_model=List[CaseResponse])
def list_matching_pool(
    current_user: AuthenticatedUser = Depends(require_role(["clinician", "admin"])),
):
    """Returns cases currently waiting in the MATCHING queue. Accessible to clinicians & admins."""
    return case_service.list_matching_pool()


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Fetches a case by ID.
    Enforces ownership:
    - Patients CANNOT view another patient's case (HTTP 403 Forbidden).
    - Clinicians can ONLY view cases in MATCHING status or cases assigned to them.
    - Admins can view all cases.
    """
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    if current_user.role == "admin":
        return case

    if current_user.role == "patient":
        if case.patientId != current_user.uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Patients can only access their own medical cases.",
            )
        return case

    if current_user.role == "clinician":
        is_assigned = bool(case.assignedClinicianId and case.assignedClinicianId == current_user.uid)
        is_matching = case.status == CaseStatus.MATCHING
        if not (is_assigned or is_matching):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Clinicians can only view cases in the MATCHING pool or cases assigned to them.",
            )
        return case

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Forbidden: Role '{current_user.role}' is not authorized to access cases.",
    )


@router.patch("/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: str,
    update_in: CaseUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Updates an existing case.
    - Only allowed when the case is in DRAFT status.
    - Enforces patient ownership.
    - Increments case version and logs audit event.
    """
    try:
        case = case_service.get_case(case_id)
        check_case_ownership(case.patientId, current_user)

        return case_service.update_case(
            case_id=case_id,
            update_in=update_in,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (CaseUpdateNotAllowedError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{case_id}", response_model=CaseResponse)
def delete_or_cancel_case(
    case_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Cancels/archives a case.
    Enforces patient ownership or admin role.
    Transitions status to CANCELLED.
    """
    try:
        case = case_service.get_case(case_id)
        check_case_ownership(case.patientId, current_user)

        return case_service.delete_case(
            case_id=case_id,
            actor_id=current_user.uid,
            actor_role=current_user.role,
            reason="Cancelled by patient/admin",
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{case_id}/submit", response_model=CaseResponse)
def submit_case(
    case_id: str,
    req: Optional[CaseSubmitRequest] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Patient submits case after initial intake.
    Idempotent: If case is already SUBMITTED, returns existing submitted case safely.
    """
    try:
        case = case_service.get_case(case_id)
        check_case_ownership(case.patientId, current_user)

        idempotency_key = req.idempotencyKey if req else None
        return case_service.submit_case(
            case_id=case_id,
            actor_id=current_user.uid,
            actor_role=current_user.role,
            idempotency_key=idempotency_key,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{case_id}/matching", response_model=CaseResponse)
def enqueue_for_matching(
    case_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Patient approves brief and enqueues into clinician matching pool.
    Transitions case to MATCHING status.
    """
    try:
        case = case_service.get_case(case_id)
        check_case_ownership(case.patientId, current_user)

        return case_service.transition_status(
            case_id=case_id,
            target_status=CaseStatus.MATCHING,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{case_id}/match", response_model=ClinicianMatchResponse)
def match_case(
    case_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Triggers or queries matching algorithm for a case.
    Filters by verification, availability, specialty, language, and queue order.
    If no clinician is available, transitions to NO_CLINICIAN_AVAILABLE.
    """
    try:
        case = case_service.get_case(case_id)
        if current_user.role == "patient":
            check_case_ownership(case.patientId, current_user)

        return clinician_service.trigger_matching(
            case_id=case_id,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{case_id}/accept", response_model=CaseResponse)
def accept_case(
    case_id: str,
    req: Optional[CaseAcceptRequest] = None,
    current_user: AuthenticatedUser = Depends(require_verified_clinician),
):
    """
    Concurrency-safe atomic case claiming.
    - RESTRICTED to verified clinicians only (HTTP 403 Forbidden for unverified clinicians).
    - Returns HTTP 409 Conflict if already claimed by another clinician or not in MATCHING status.
    """
    clinician_id = current_user.uid

    try:
        return case_service.accept_case_atomic(case_id=case_id, clinician_id=clinician_id)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CaseConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post("/{case_id}/decline", response_model=CaseResponse)
def decline_case(
    case_id: str,
    req: Optional[CaseDeclineRequest] = None,
    current_user: AuthenticatedUser = Depends(require_verified_clinician),
):
    """
    Clinician declines case.
    Re-evaluates remaining available clinicians.
    If pool is exhausted, automatically transitions case to NO_CLINICIAN_AVAILABLE.
    """
    try:
        reason = req.reason if req else "Clinician declined case"
        return clinician_service.decline_case(
            case_id=case_id,
            clinician_id=current_user.uid,
            reason=reason,
            actor_id=current_user.uid,
            actor_role=current_user.role,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))



@router.post("/{case_id}/status", response_model=CaseResponse)
def update_case_status(
    case_id: str,
    req: StateTransitionRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Transitions status across lifecycle (e.g. IN_CONSULTATION, COMPLETED, ESCALATED).
    Enforces assigned clinician / ownership checks.
    """
    try:
        case = case_service.get_case(case_id)
        if current_user.role == "clinician" and case.assignedClinicianId != current_user.uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Only the assigned clinician can update case consultation status.",
            )
        if current_user.role == "patient" and case.patientId != current_user.uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Cannot modify another patient's case.",
            )

        return case_service.transition_status(
            case_id=case_id,
            target_status=req.targetStatus,
            actor_id=current_user.uid,
            actor_role=current_user.role,
            reason=req.reason,
        )
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
