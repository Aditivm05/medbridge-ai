from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime


class ClinicianSpecialty(str, Enum):
    GENERAL_MEDICINE = "general_medicine"
    EMERGENCY_MEDICINE = "emergency_medicine"
    PEDIATRICS = "pediatrics"
    CARDIOLOGY = "cardiology"
    INTERNAL_MEDICINE = "internal_medicine"


class ClinicianAvailability(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"


class ClinicianVerificationStatus(str, Enum):
    VERIFIED = "verified"
    PENDING = "pending"
    REJECTED = "rejected"


class ClinicianProfile(BaseModel):
    clinicianId: str
    userId: str
    fullName: str
    licenseNumber: str
    specialty: ClinicianSpecialty
    languages: List[str] = Field(default_factory=lambda: ["en"])
    verificationStatus: ClinicianVerificationStatus = ClinicianVerificationStatus.VERIFIED
    availability: ClinicianAvailability = ClinicianAvailability.AVAILABLE
    isDemo: bool = True  # Always explicit DEMO / SIMULATED marking
    currentCaseId: Optional[str] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class ClinicianAvailabilityUpdateRequest(BaseModel):
    availability: ClinicianAvailability
    currentCaseId: Optional[str] = None


class CaseDeclineRequest(BaseModel):
    reason: Optional[str] = Field(default="Clinician unavailable or out of scope")


class ClinicianMatchItem(BaseModel):
    clinicianId: str
    fullName: str
    licenseNumber: str
    specialty: ClinicianSpecialty
    languages: List[str]
    matchScore: int
    isExactSpecialtyMatch: bool
    availability: ClinicianAvailability = ClinicianAvailability.AVAILABLE
    isDemo: bool = True


class ClinicianMatchResponse(BaseModel):
    caseId: str
    status: str
    matches: List[ClinicianMatchItem]
    matchedCount: int
