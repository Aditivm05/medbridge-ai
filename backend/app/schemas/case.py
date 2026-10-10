from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime
from app.core.state_machine import CaseStatus


class RequestedUrgency(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class CaseCreate(BaseModel):
    patientId: Optional[str] = None
    chiefComplaint: str = Field(..., min_length=5, max_length=1000)
    duration: str = Field(..., min_length=2, max_length=100)
    requestedUrgency: RequestedUrgency
    patientLanguage: str = Field("en", description="en | hi | mr")
    idempotencyKey: str = Field(..., description="UUID to prevent duplicate case creation")


class CaseUpdate(BaseModel):
    chiefComplaint: Optional[str] = Field(None, min_length=5, max_length=1000)
    duration: Optional[str] = Field(None, min_length=2, max_length=100)
    requestedUrgency: Optional[RequestedUrgency] = None
    patientLanguage: Optional[str] = Field(None, description="en | hi | mr")


class CaseSubmitRequest(BaseModel):
    idempotencyKey: Optional[str] = None


class CaseResponse(BaseModel):
    caseId: str
    patientId: str
    assignedClinicianId: Optional[str] = None
    requestedUrgency: RequestedUrgency
    status: CaseStatus
    idempotencyKey: str
    chiefComplaint: str
    duration: str
    patientLanguage: str
    documentCount: int = 0
    doctorBriefId: Optional[str] = None
    consultationId: Optional[str] = None
    version: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime
    updatedAt: datetime
    submittedAt: Optional[datetime] = None
    acceptedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StateTransitionRequest(BaseModel):
    targetStatus: CaseStatus
    reason: Optional[str] = None
    idempotencyKey: Optional[str] = None


class CaseAcceptRequest(BaseModel):
    clinicianId: Optional[str] = None
