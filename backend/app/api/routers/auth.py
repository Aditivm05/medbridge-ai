import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.auth import (
    get_current_user,
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
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Sets custom claims (role and clinician verification).
    RESTRICTION: Admin-only in production, or allowed when running under the Firebase Auth emulator.
    """
    is_emulator = bool(
        os.getenv("FIREBASE_AUTH_EMULATOR_HOST")
        or settings.FIREBASE_AUTH_EMULATOR_HOST
    )
    is_admin = current_user.role == "admin"

    if not is_admin and not is_emulator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Updating custom claims requires admin privileges or an active emulator environment.",
        )

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
