from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime


class AuditEventType(str, Enum):
    CASE_CREATED = "CASE_CREATED"
    CASE_UPDATED = "CASE_UPDATED"
    CASE_SUBMITTED = "CASE_SUBMITTED"
    CASE_MATCHING_ENQUEUED = "CASE_MATCHING_ENQUEUED"
    CASE_ACCEPTED = "CASE_ACCEPTED"
    CASE_DECLINED = "CASE_DECLINED"
    CASE_IN_CONSULTATION = "CASE_IN_CONSULTATION"
    CASE_COMPLETED = "CASE_COMPLETED"
    CASE_CANCELLED = "CASE_CANCELLED"
    CASE_ESCALATED = "CASE_ESCALATED"
    CASE_FAILED = "CASE_FAILED"
    CASE_NO_CLINICIAN = "CASE_NO_CLINICIAN"
    DOC_UPLOADED = "DOC_UPLOADED"
    DOC_UPLOAD_REJECTED = "DOC_UPLOAD_REJECTED"
    DOC_VIEWED = "DOC_VIEWED"
    DOC_VIEW_DENIED = "DOC_VIEW_DENIED"
    DOC_TEXT_EXTRACTED = "DOC_TEXT_EXTRACTED"
    DOC_EXTRACTION_FAILED = "DOC_EXTRACTION_FAILED"
    DOC_AI_EXTRACTED = "DOC_AI_EXTRACTED"
    BRIEF_GENERATED = "BRIEF_GENERATED"
    BRIEF_EDITED = "BRIEF_EDITED"
    BRIEF_APPROVED = "BRIEF_APPROVED"
    BRIEF_CLINICIAN_REVIEWED = "BRIEF_CLINICIAN_REVIEWED"
    AUTH_FAILED = "AUTH_FAILED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"


class AuditEventCreate(BaseModel):
    caseId: Optional[str] = None
    actorId: str
    actorRole: str
    eventType: AuditEventType
    ipAddress: Optional[str] = None
    userAgent: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class AuditEventResponse(AuditEventCreate):
    eventId: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)
