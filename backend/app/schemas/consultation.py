from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class ConsultationType(str, Enum):
    TEXT_BASED_SIMULATED = "text_based_consultation_simulated"


class ConsultationCreate(BaseModel):
    clinicianNotes: str = Field(..., min_length=10, max_length=5000)
    provisionalCareAdvice: str = Field(..., min_length=10, max_length=2000, description="General care coordination guidance (non-prescription)")
    isSimulated: bool = Field(True, description="Explicit DEMO / SIMULATED tagging")


class ConsultationResponse(BaseModel):
    consultationId: str
    caseId: str
    clinicianId: str
    patientId: str
    consultationType: ConsultationType = ConsultationType.TEXT_BASED_SIMULATED
    isSimulated: bool = True
    clinicianNotes: str
    provisionalCareAdvice: str
    startedAt: datetime
    endedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FollowUpStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FollowUpCreate(BaseModel):
    required: bool
    recommendedDate: str = Field(..., description="Target follow-up date YYYY-MM-DD")
    instructions: str = Field(..., min_length=5, max_length=1000)


class FollowUpResponse(BaseModel):
    followUpId: str
    caseId: str
    patientId: str
    clinicianId: str
    required: bool
    recommendedDate: str
    status: FollowUpStatus
    instructions: str
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)
