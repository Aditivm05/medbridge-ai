import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.auth import (
    get_current_user,
    require_role,
    set_user_custom_claims,
    AuthenticatedUser,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class SetClaimsRequest(BaseModel):
    uid: str
    role: str = Field(description="'patient' | 'clinician' | 'admin'")
    is_verified_clinician: bool = False
    extra_claims: Optional[Dict[str, Any]] = None


@router.get("/me")
def get_my_profile(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Returns the authenticated user's verified token claims and role."""
    return {
        "uid": current_user.uid,
        "email": current_user.email,
        "role": current_user.role,
        "isVerifiedClinician": current_user.is_verified_clinician,
        "displayName": current_user.display_name,
        "customClaims": current_user.custom_claims,
    }


@router.post("/claims")
def update_user_claims(
    req: SetClaimsRequest,
    current_user: AuthenticatedUser = Depends(require_role(["admin"])),
):
    """
    Sets custom claims (role and clinician verification).
    RESTRICTION: Restricted to administrators.
    """

    updated = set_user_custom_claims(
        uid=req.uid,
        role=req.role,
        is_verified_clinician=req.is_verified_clinician,
        extra_claims=req.extra_claims,
    )
    return {
        "status": "success",
        "uid": req.uid,
        "claims": updated,
    }
