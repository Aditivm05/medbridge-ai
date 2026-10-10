import json
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from app.core.state_machine import CaseStatus

ALLOWED_CASE_METADATA_KEYS = frozenset({
    "symptoms",
    "knownConditions",
    "medications",
    "allergies",
    "vitals",
})
MAX_METADATA_TOTAL_BYTES = 10 * 1024  # 10 KB
MAX_METADATA_STR_FIELD_LEN = 2000
MAX_METADATA_LIST_ITEMS = 30
MAX_METADATA_LIST_ITEM_LEN = 200
MAX_METADATA_DICT_ITEMS = 15
MAX_METADATA_DICT_VAL_LEN = 100


def validate_case_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates patient intake metadata against an allowlist of permitted keys and strict size limits.
    Prevents arbitrary keys, injection of server-controlled flags/counters, and document bloat.
    """
    if not isinstance(meta, dict):
        raise ValueError("metadata must be a dictionary")

    for k in meta.keys():
        if not isinstance(k, str):
            raise ValueError("All metadata keys must be strings")
        if k not in ALLOWED_CASE_METADATA_KEYS:
            raise ValueError(
                f"Disallowed metadata key '{k}'. "
                f"Allowed keys are: {', '.join(sorted(ALLOWED_CASE_METADATA_KEYS))}"
            )

    try:
        serialized = json.dumps(meta)
    except Exception as e:
        raise ValueError(f"metadata must be JSON-serializable: {e}")
    if len(serialized.encode("utf-8")) > MAX_METADATA_TOTAL_BYTES:
        raise ValueError(f"metadata size exceeds maximum limit of {MAX_METADATA_TOTAL_BYTES} bytes")

    if "symptoms" in meta and meta["symptoms"] is not None:
        val = meta["symptoms"]
        if isinstance(val, list):
            if len(val) > MAX_METADATA_LIST_ITEMS:
                raise ValueError(f"symptoms list cannot exceed {MAX_METADATA_LIST_ITEMS} items")
            for item in val:
                if not isinstance(item, str) or len(item) > MAX_METADATA_LIST_ITEM_LEN:
                    raise ValueError(f"Each symptom item must be a string <= {MAX_METADATA_LIST_ITEM_LEN} characters")
        elif isinstance(val, str):
            if len(val) > MAX_METADATA_STR_FIELD_LEN:
                raise ValueError(f"symptoms string cannot exceed {MAX_METADATA_STR_FIELD_LEN} characters")
        else:
            raise ValueError("symptoms must be a list of strings or a string")

    for text_field in ("knownConditions", "medications", "allergies"):
        if text_field in meta and meta[text_field] is not None:
            val = meta[text_field]
            if not isinstance(val, str):
                raise ValueError(f"{text_field} must be a string")
            if len(val) > MAX_METADATA_STR_FIELD_LEN:
                raise ValueError(f"{text_field} cannot exceed {MAX_METADATA_STR_FIELD_LEN} characters")

    if "vitals" in meta and meta["vitals"] is not None:
        val = meta["vitals"]
        if isinstance(val, dict):
            if len(val) > MAX_METADATA_DICT_ITEMS:
                raise ValueError(f"vitals cannot exceed {MAX_METADATA_DICT_ITEMS} entries")
            for vk, vv in val.items():
                if not isinstance(vk, str) or len(vk) > 50:
                    raise ValueError("vitals keys must be strings <= 50 characters")
                if not isinstance(vv, (str, int, float)) or (isinstance(vv, str) and len(vv) > MAX_METADATA_DICT_VAL_LEN):
                    raise ValueError(f"vitals values must be string (<= {MAX_METADATA_DICT_VAL_LEN} chars), int, or float")
        elif isinstance(val, str):
            if len(val) > MAX_METADATA_STR_FIELD_LEN:
                raise ValueError(f"vitals string cannot exceed {MAX_METADATA_STR_FIELD_LEN} characters")
        else:
            raise ValueError("vitals must be a dictionary or a string")

    return meta


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
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return None
        return validate_case_metadata(v)


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
