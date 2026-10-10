from fastapi import APIRouter, Depends
from typing import List, Optional
from app.schemas.audit import AuditEventResponse
from app.services.audit_service import audit_service
from app.core.auth import require_role, AuthenticatedUser

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=List[AuditEventResponse])
def get_audit_trail(
    caseId: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(require_role(["admin", "clinician"])),
):
    """Immutable audit trail access restricted to clinicians and administrators."""
    if caseId:
        return audit_service.get_events_for_case(caseId)
    return audit_service.list_recent_events()


@router.get("/cases/{case_id}", response_model=List[AuditEventResponse])
def get_case_audit_trail(
    case_id: str,
    current_user: AuthenticatedUser = Depends(require_role(["admin", "clinician"])),
):
    """Retrieves immutable audit trail for a specific case. Restricted to clinicians and administrators."""
    return audit_service.get_events_for_case(case_id)
