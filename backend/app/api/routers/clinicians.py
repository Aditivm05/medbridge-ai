"""
Clinician API Endpoints
Manages clinician profiles, demo seeding, availability updates, and matching queries.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.auth import get_current_user, require_role, require_verified_clinician, AuthenticatedUser
from app.schemas.clinician import (
    ClinicianProfile,
    ClinicianSpecialty,
    ClinicianAvailability,
    ClinicianVerificationStatus,
    ClinicianAvailabilityUpdateRequest,
)
from app.schemas.case import CaseResponse
from app.services.clinician_service import (
    clinician_service,
    ClinicianNotFoundError,
)
from app.services.case_service import case_service

router = APIRouter(prefix="/clinicians", tags=["clinicians"])


@router.post("/seed", response_model=List[ClinicianProfile])
def seed_demo_clinicians(
    current_user: AuthenticatedUser = Depends(require_role(["admin"])),
):
    """
    Seeds labelled [DEMO / SIMULATED] clinicians into Firestore.
    Restricted to administrator callers. Idempotent operation.
    """
    return clinician_service.seed_default_clinicians()


@router.get("", response_model=List[ClinicianProfile])
def list_clinicians(
    specialty: Optional[ClinicianSpecialty] = None,
    availability: Optional[ClinicianAvailability] = None,
    language: Optional[str] = None,
    verification_status: Optional[ClinicianVerificationStatus] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Lists clinicians with optional filtering."""
    return clinician_service.list_clinicians(
        specialty=specialty,
        availability=availability,
        language=language,
        verification_status=verification_status,
    )


@router.get("/matching-pool", response_model=List[CaseResponse])
def get_matching_pool(
    current_user: AuthenticatedUser = Depends(require_verified_clinician),
):
    """Returns cases currently available in MATCHING status for verified clinicians."""
    return case_service.list_matching_pool()


@router.get("/{clinician_id}", response_model=ClinicianProfile)
def get_clinician(
    clinician_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieves clinician profile by ID."""
    try:
        return clinician_service.get_clinician(clinician_id)
    except ClinicianNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{clinician_id}/availability", response_model=ClinicianProfile)
def update_clinician_availability(
    clinician_id: str,
    req: ClinicianAvailabilityUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Updates clinician availability (available, busy, offline).
    Only the clinician themselves or an admin can update availability.
    """
    if current_user.role != "admin" and current_user.uid != clinician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Cannot update availability for another clinician.",
        )

    try:
        return clinician_service.update_availability(
            clinician_id=clinician_id,
            availability=req.availability,
            current_case_id=req.currentCaseId,
        )
    except ClinicianNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
