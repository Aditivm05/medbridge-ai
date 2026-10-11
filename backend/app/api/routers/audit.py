from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.schemas.audit import AuditEventResponse
from app.services.audit_service import audit_service
from app.services.case_service import case_service, CaseNotFoundError
from app.core.auth import require_role, AuthenticatedUser

router = APIRouter(prefix="/audit", tags=["audit"])


def _authorize_case_audit_access(case_id: str, current_user: AuthenticatedUser) -> None:
    """Verifies that the case exists and the clinician is assigned (or caller is admin)."""
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    if current_user.role == "admin":
        return

    if current_user.role == "clinician":
        if case.assignedClinicianId != current_user.uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Clinicians can only access audit events for cases assigned to them.",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Forbidden: Role '{current_user.role}' is not authorized to access audit events.",
    )


@router.get("", response_model=List[AuditEventResponse])
def get_audit_trail(
    caseId: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(require_role(["admin", "clinician"])),
):
    """
    Audit trail access:
    - System-wide audit log (no caseId) is restricted to administrators.
    - Case-specific audit log is restricted to administrators and the assigned clinician.
    """
    if caseId:
        _authorize_case_audit_access(caseId, current_user)
        return audit_service.get_events_for_case(caseId)

    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: System-wide audit trail access is restricted to administrators.",
        )
    return audit_service.list_recent_events()


@router.get("/cases/{case_id}", response_model=List[AuditEventResponse])
def get_case_audit_trail(
    case_id: str,
    current_user: AuthenticatedUser = Depends(require_role(["admin", "clinician"])),
):
    """Retrieves immutable audit trail for a specific case. Restricted to assigned clinicians and administrators."""
    _authorize_case_audit_access(case_id, current_user)
    return audit_service.get_events_for_case(case_id)
