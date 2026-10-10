"""
Firestore Model Converters & Deserializers
Handles bi-directional conversion between Firestore document snapshots/dictionaries
and Pydantic schemas, supporting Firestore Timestamp conversion and schema validation.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from app.schemas.case import CaseResponse, CaseCreate, RequestedUrgency
from app.schemas.audit import AuditEventResponse, AuditEventType
from app.schemas.document import DocumentResponse, ExtractionStatus, PageText
from app.core.state_machine import CaseStatus


def firestore_timestamp_to_datetime(val: Any) -> Optional[datetime]:
    """Converts a Firestore Timestamp object or ISO string to a Python datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    # If it is a google.cloud.firestore_v1._helpers.DatetimeWithNanoseconds or Timestamp
    if hasattr(val, "to_datetime"):
        return val.to_datetime()
    if hasattr(val, "timestamp"):
        return datetime.utcfromtimestamp(val.timestamp())
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return datetime.utcnow()
    return None


def case_to_firestore_dict(case: CaseResponse) -> Dict[str, Any]:
    """Serializes a CaseResponse Pydantic model to a Firestore-compatible document dictionary."""
    data = case.model_dump()
    # Ensure enum values are stored as strings
    data["status"] = case.status.value
    data["requestedUrgency"] = case.requestedUrgency.value
    # Format datetimes
    for date_field in ["createdAt", "updatedAt", "submittedAt", "acceptedAt", "completedAt"]:
        if data.get(date_field) and isinstance(data[date_field], datetime):
            data[date_field] = data[date_field].isoformat()
    return data


def case_from_firestore_dict(doc_id: str, data: Dict[str, Any]) -> CaseResponse:
    """Deserializes a Firestore document dictionary into a CaseResponse Pydantic model."""
    doc_data = dict(data)
    doc_data["caseId"] = doc_id
    
    # Handle status enum
    if "status" in doc_data and isinstance(doc_data["status"], str):
        doc_data["status"] = CaseStatus(doc_data["status"])
    
    # Handle requestedUrgency enum
    if "requestedUrgency" in doc_data and isinstance(doc_data["requestedUrgency"], str):
        doc_data["requestedUrgency"] = RequestedUrgency(doc_data["requestedUrgency"])
    
    # Handle timestamps
    for date_field in ["createdAt", "updatedAt", "submittedAt", "acceptedAt", "completedAt"]:
        if date_field in doc_data:
            doc_data[date_field] = firestore_timestamp_to_datetime(doc_data[date_field])
    
    if not doc_data.get("createdAt"):
        doc_data["createdAt"] = datetime.utcnow()
    if not doc_data.get("updatedAt"):
        doc_data["updatedAt"] = datetime.utcnow()
        
    return CaseResponse.model_validate(doc_data)


def audit_event_to_firestore_dict(event: AuditEventResponse) -> Dict[str, Any]:
    """Serializes an AuditEventResponse to a Firestore-compatible document dictionary."""
    data = event.model_dump()
    data["eventType"] = event.eventType.value
    if isinstance(data.get("timestamp"), datetime):
        data["timestamp"] = data["timestamp"].isoformat()
    return data


def audit_event_from_firestore_dict(doc_id: str, data: Dict[str, Any]) -> AuditEventResponse:
    """Deserializes a Firestore document dictionary into an AuditEventResponse model."""
    doc_data = dict(data)
    doc_data["eventId"] = doc_id
    if "eventType" in doc_data and isinstance(doc_data["eventType"], str):
        doc_data["eventType"] = AuditEventType(doc_data["eventType"])
    if "timestamp" in doc_data:
        doc_data["timestamp"] = firestore_timestamp_to_datetime(doc_data["timestamp"]) or datetime.utcnow()
    return AuditEventResponse.model_validate(doc_data)


def document_to_firestore_dict(doc: DocumentResponse) -> Dict[str, Any]:
    """Serializes a DocumentResponse Pydantic model to a Firestore-compatible document dictionary."""
    data = doc.model_dump()
    data["extractionStatus"] = doc.extractionStatus.value
    if data.get("pages"):
        data["pages"] = [
            {
                "pageNumber": p["pageNumber"],
                "text": p["text"],
                "charCount": p["charCount"],
                "status": p["status"].value if hasattr(p["status"], "value") else str(p["status"]),
                "source": p.get("source", "PDF_TEXT"),
            }
            for p in data["pages"]
        ]
    for date_field in ["uploadedAt", "extractedAt"]:
        if data.get(date_field) and isinstance(data[date_field], datetime):
            data[date_field] = data[date_field].isoformat()
    return data


def document_from_firestore_dict(doc_id: str, data: Dict[str, Any]) -> DocumentResponse:
    """Deserializes a Firestore document dictionary into a DocumentResponse model."""
    doc_data = dict(data)
    doc_data["documentId"] = doc_id
    if "extractionStatus" in doc_data and isinstance(doc_data["extractionStatus"], str):
        doc_data["extractionStatus"] = ExtractionStatus(doc_data["extractionStatus"])
    if "pages" in doc_data and isinstance(doc_data["pages"], list):
        parsed_pages = []
        for p in doc_data["pages"]:
            p_dict = dict(p)
            if "status" in p_dict and isinstance(p_dict["status"], str):
                p_dict["status"] = ExtractionStatus(p_dict["status"])
            parsed_pages.append(PageText.model_validate(p_dict))
        doc_data["pages"] = parsed_pages
    for date_field in ["uploadedAt", "extractedAt"]:
        if date_field in doc_data:
            doc_data[date_field] = firestore_timestamp_to_datetime(doc_data[date_field])
    if not doc_data.get("uploadedAt"):
        doc_data["uploadedAt"] = datetime.utcnow()
    return DocumentResponse.model_validate(doc_data)
