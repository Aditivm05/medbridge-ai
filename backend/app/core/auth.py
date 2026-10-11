import os
import json
import base64
import logging
from typing import Optional, Dict, Any, List, Callable
from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
from app.core.config import settings

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)

# Initialize Firebase Admin App once (supports Auth emulator)
_firebase_initialized = False


def init_firebase_admin():
    global _firebase_initialized
    if _firebase_initialized:
        return

    # Check emulator host environment variable
    if settings.FIREBASE_AUTH_EMULATOR_HOST:
        os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = settings.FIREBASE_AUTH_EMULATOR_HOST

    try:
        if not firebase_admin._apps:
            # When using emulators or ADC, initializing with projectId is sufficient
            firebase_admin.initialize_app(
                options={"projectId": settings.FIREBASE_PROJECT_ID},
            )
        _firebase_initialized = True
        logger.info(f"Firebase Admin SDK initialized (Project: {settings.FIREBASE_PROJECT_ID})")
    except Exception as e:
        logger.warning(f"Could not initialize Firebase Admin SDK: {e}. Falling back to dev token mode.")


init_firebase_admin()


class AuthenticatedUser(BaseModel):
    uid: str
    email: Optional[str] = None
    role: str = "patient"  # "patient" | "clinician" | "admin"
    is_verified_clinician: bool = False
    display_name: Optional[str] = None
    custom_claims: Dict[str, Any] = Field(default_factory=dict)


# In-memory user claims override for testing and development
_custom_claims_store: Dict[str, Dict[str, Any]] = {
    "patient_demo_1": {"role": "patient", "is_verified_clinician": False},
    "patient_demo_2": {"role": "patient", "is_verified_clinician": False},
    "clinician_verified_1": {"role": "clinician", "is_verified_clinician": True, "licenseNumber": "MMC-SIM-91823"},
    "clinician_unverified_2": {"role": "clinician", "is_verified_clinician": False, "licenseNumber": "MMC-PENDING-404"},
    "admin_demo_1": {"role": "admin", "is_verified_clinician": False},
}


def set_user_custom_claims(uid: str, role: str, is_verified_clinician: bool = False, extra_claims: Optional[Dict[str, Any]] = None):
    """Sets role and verification claims on a user (in-memory and Firebase Auth if available)."""
    claims = {
        "role": role,
        "is_verified_clinician": is_verified_clinician,
        **(extra_claims or {}),
    }
    _custom_claims_store[uid] = claims

    # If Firebase Admin is available, set custom user claims in Firebase Auth as well
    try:
        firebase_auth.set_custom_user_claims(uid, claims)
    except Exception as e:
        logger.debug(f"Could not persist custom claims to Firebase Auth emulator: {e}")
    return claims


def is_demo_auth_enabled() -> bool:
    """
    Checks if deterministic demo/mock tokens ('mock-token-*', 'dev-token-*', 'test-token-*', 'claims.*') are allowed.
    Rules:
    1. If ENVIRONMENT == 'production' (in settings or os.environ), ALWAYS disabled (returns False).
    2. Otherwise, enabled ONLY if DEMO_AUTH_ENABLED=true (in settings or os.environ) OR TESTING=1 (in os.environ).
    3. Default is False.
    """
    env = os.environ.get("ENVIRONMENT") or settings.ENVIRONMENT
    if env.lower() == "production":
        return False
    if os.environ.get("TESTING") == "1":
        return True
    if os.environ.get("DEMO_AUTH_ENABLED", "").lower() in ("true", "1") or getattr(settings, "DEMO_AUTH_ENABLED", False):
        return True
    return False


def verify_id_token(token: str) -> AuthenticatedUser:
    """
    Decodes and verifies a token.
    Supports:
    1. Deterministic test/dev tokens: 'mock-token-<role>', 'dev-token-...', 'bearer-patient-1', etc.
    2. Base64 JSON tokens: 'claims.<base64>'
    3. Firebase ID tokens verified via Firebase Admin SDK (with emulator support).
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or empty Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clean_token = token.strip()

    # 1. Deterministic Test / Development Tokens
    if clean_token.startswith("mock-token-") or clean_token.startswith("dev-token-") or clean_token.startswith("test-token-"):
        if not is_demo_auth_enabled():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mock tokens are disabled in this environment (requires DEMO_AUTH_ENABLED=true or TESTING=1 outside production)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        parts = clean_token.lower()
        if "patient-1" in parts or "patient_1" in parts or "patient-001" in parts:
            uid = "patient_demo_1"
            role = "patient"
            is_verified = False
        elif "patient-2" in parts or "patient_2" in parts or "patient-002" in parts:
            uid = "patient_demo_2"
            role = "patient"
            is_verified = False
        elif "clinician-verified" in parts or "clinician_verified" in parts or "doc-verified" in parts:
            uid = "clinician_verified_1"
            role = "clinician"
            is_verified = True
        elif "clinician-unverified" in parts or "clinician_unverified" in parts or "doc-unverified" in parts:
            uid = "clinician_unverified_2"
            role = "clinician"
            is_verified = False
        elif "admin" in parts:
            uid = "admin_demo_1"
            role = "admin"
            is_verified = False
        else:
            # Fallback parse: e.g. mock-token-patient-customid or mock-token-demo_doc_sharma
            uid = clean_token.replace("mock-token-", "").replace("dev-token-", "").replace("test-token-", "")
            role = "clinician" if ("clinician" in uid or "doc" in uid) else ("admin" if "admin" in uid else "patient")
            is_verified = ("verified" in uid or ("doc" in uid and "pending" not in uid and "unverified" not in uid)) and "unverified" not in uid

        # Check if overridden in store
        stored = _custom_claims_store.get(uid, {})
        final_role = stored.get("role", role)
        final_verified = stored.get("is_verified_clinician", is_verified)

        return AuthenticatedUser(
            uid=uid,
            email=f"{uid}@example.com",
            role=final_role,
            is_verified_clinician=final_verified,
            display_name=f"User {uid}",
            custom_claims=_custom_claims_store.get(uid, {"role": final_role, "is_verified_clinician": final_verified}),
        )

    # 2. Base64 JSON token for testing custom payloads: e.g. 'claims.<base64>'
    if clean_token.startswith("claims."):
        if not is_demo_auth_enabled():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mock claims tokens are disabled in this environment",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            raw_b64 = clean_token.split("claims.", 1)[1]
            padded = raw_b64 + "=" * (-len(raw_b64) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
            return AuthenticatedUser(
                uid=data.get("uid", "custom_user"),
                email=data.get("email"),
                role=data.get("role", "patient"),
                is_verified_clinician=bool(data.get("is_verified_clinician", False)),
                display_name=data.get("display_name"),
                custom_claims=data.get("custom_claims", {}),
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed base64 token claims",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 3. Real Firebase ID token verification via Firebase Admin SDK
    try:
        decoded = firebase_auth.verify_id_token(clean_token)
        uid = decoded.get("uid") or decoded.get("sub")
        claims = _custom_claims_store.get(uid, {})

        role = decoded.get("role") or claims.get("role") or "patient"
        is_verified = bool(decoded.get("is_verified_clinician") or claims.get("is_verified_clinician", False))

        return AuthenticatedUser(
            uid=uid,
            email=decoded.get("email"),
            role=role,
            is_verified_clinician=is_verified,
            display_name=decoded.get("name"),
            custom_claims=decoded,
        )
    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired ID token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> AuthenticatedUser:
    """Dependency that extracts and validates the Authorization: Bearer <token> header."""
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_id_token(creds.credentials)


def require_role(allowed_roles: List[str]) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Dependency factory that restricts access to users with specified roles."""
    def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Insufficient role permissions. Required one of {allowed_roles}, got '{user.role}'.",
            )
        return user
    return role_checker


def require_verified_clinician(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Dependency that enforces verified clinician status for clinical actions (e.g. claiming cases)."""
    if user.role != "clinician":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Clinician role required. Current role is '{user.role}'.",
        )
    if not user.is_verified_clinician:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only verified clinicians with validated medical licenses can accept cases or access clinical workspaces.",
        )
    return user


def check_case_ownership(case_patient_id: str, current_user: AuthenticatedUser) -> None:
    """
    Ownership check:
    - If user is a patient: they can ONLY access their own case.
    - If user is a clinician or admin: permitted.
    """
    if current_user.role == "patient" and case_patient_id != current_user.uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Patients can only access their own medical cases.",
        )
