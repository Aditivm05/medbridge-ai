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


def doctor_brief_to_firestore_dict(brief: Any) -> Dict[str, Any]:
    """Serializes a DoctorBrief Pydantic model to a Firestore-compatible document dictionary."""
    data = brief.model_dump(mode="json")
    if hasattr(brief.briefStatus, "value"):
        data["briefStatus"] = brief.briefStatus.value
    return data


def doctor_brief_from_firestore_dict(doc_id: str, data: Dict[str, Any]) -> Any:
    """Deserializes a Firestore document dictionary into a DoctorBrief model."""
    from app.schemas.doctor_brief import DoctorBrief, BriefStatus
    doc_data = dict(data)
    doc_data["briefId"] = data.get("briefId") or doc_id
    if "briefStatus" in doc_data and isinstance(doc_data["briefStatus"], str):
        doc_data["briefStatus"] = BriefStatus(doc_data["briefStatus"])
    for date_field in ["createdAt", "updatedAt", "lastEditedAt", "approvedAt", "reviewedAt"]:
        if date_field in doc_data and doc_data[date_field]:
            doc_data[date_field] = firestore_timestamp_to_datetime(doc_data[date_field])
    return DoctorBrief.model_validate(doc_data)


def clinician_to_firestore_dict(clinician: Any) -> Dict[str, Any]:
    """Serializes a ClinicianProfile model to a Firestore-compatible document dictionary."""
    data = clinician.model_dump(mode="json")
    if hasattr(clinician.specialty, "value"):
        data["specialty"] = clinician.specialty.value
    if hasattr(clinician.verificationStatus, "value"):
        data["verificationStatus"] = clinician.verificationStatus.value
    if hasattr(clinician.availability, "value"):
        data["availability"] = clinician.availability.value
    if data.get("createdAt") and isinstance(data["createdAt"], datetime):
        data["createdAt"] = data["createdAt"].isoformat()
    return data


def clinician_from_firestore_dict(doc_id: str, data: Dict[str, Any]) -> Any:
    """Deserializes a Firestore document dictionary into a ClinicianProfile model."""
    from app.schemas.clinician import ClinicianProfile, ClinicianSpecialty, ClinicianAvailability, ClinicianVerificationStatus
    doc_data = dict(data)
    doc_data["clinicianId"] = doc_id
    if "specialty" in doc_data and isinstance(doc_data["specialty"], str):
        doc_data["specialty"] = ClinicianSpecialty(doc_data["specialty"])
    if "verificationStatus" in doc_data and isinstance(doc_data["verificationStatus"], str):
        doc_data["verificationStatus"] = ClinicianVerificationStatus(doc_data["verificationStatus"])
    if "availability" in doc_data and isinstance(doc_data["availability"], str):
        doc_data["availability"] = ClinicianAvailability(doc_data["availability"])
    if "createdAt" in doc_data and doc_data["createdAt"]:
        doc_data["createdAt"] = firestore_timestamp_to_datetime(doc_data["createdAt"])
    if not doc_data.get("createdAt"):
        doc_data["createdAt"] = datetime.utcnow()
    return ClinicianProfile.model_validate(doc_data)


def consultation_to_firestore_dict(consultation: Any) -> Dict[str, Any]:
    """Serializes a ConsultationResponse or ConsultationCreate model to Firestore format."""
    data = consultation.model_dump(mode="json")
    if hasattr(consultation, "consultationType") and hasattr(consultation.consultationType, "value"):
        data["consultationType"] = consultation.consultationType.value
    for date_field in ["startedAt", "endedAt"]:
        if data.get(date_field) and isinstance(data[date_field], datetime):
            data[date_field] = data[date_field].isoformat()
    return data


def consultation_from_firestore_dict(doc_id: str, data: Dict[str, Any]) -> Any:
    """Deserializes a Firestore document dictionary into a ConsultationResponse model."""
    from app.schemas.consultation import ConsultationResponse, ConsultationType
    doc_data = dict(data)
    doc_data["consultationId"] = doc_data.get("consultationId", doc_id)
    if "consultationType" in doc_data and isinstance(doc_data["consultationType"], str):
        doc_data["consultationType"] = ConsultationType(doc_data["consultationType"])
    for date_field in ["startedAt", "endedAt"]:
        if date_field in doc_data and doc_data[date_field]:
            doc_data[date_field] = firestore_timestamp_to_datetime(doc_data[date_field])
    if not doc_data.get("startedAt"):
        doc_data["startedAt"] = datetime.utcnow()
    return ConsultationResponse.model_validate(doc_data)


def follow_up_to_firestore_dict(follow_up: Any) -> Dict[str, Any]:
    """Serializes a FollowUpResponse model to Firestore format."""
    data = follow_up.model_dump(mode="json")
    if hasattr(follow_up, "status") and hasattr(follow_up.status, "value"):
        data["status"] = follow_up.status.value
    if data.get("createdAt") and isinstance(data["createdAt"], datetime):
        data["createdAt"] = data["createdAt"].isoformat()
    return data


def follow_up_from_firestore_dict(doc_id: str, data: Dict[str, Any]) -> Any:
    """Deserializes a Firestore document dictionary into a FollowUpResponse model."""
    from app.schemas.consultation import FollowUpResponse, FollowUpStatus
    doc_data = dict(data)
    doc_data["followUpId"] = doc_data.get("followUpId", doc_id)
    if "status" in doc_data and isinstance(doc_data["status"], str):
        doc_data["status"] = FollowUpStatus(doc_data["status"])
    if "createdAt" in doc_data and doc_data["createdAt"]:
        doc_data["createdAt"] = firestore_timestamp_to_datetime(doc_data["createdAt"])
    if not doc_data.get("createdAt"):
        doc_data["createdAt"] = datetime.utcnow()
    return FollowUpResponse.model_validate(doc_data)
