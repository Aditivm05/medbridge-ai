from app.schemas.user import UserRole, UserProfile, UserCreate
from app.schemas.patient import PatientProfile, EmergencyContact
from app.schemas.clinician import (
    ClinicianProfile,
    ClinicianSpecialty,
    ClinicianAvailability,
    ClinicianVerificationStatus,
)
from app.schemas.case import (
    RequestedUrgency,
    CaseCreate,
    CaseResponse,
    StateTransitionRequest,
    CaseAcceptRequest,
)
from app.schemas.document import (
    DocumentUploadIntentRequest,
    DocumentUploadIntentResponse,
    DocumentResponse,
    validate_magic_bytes,
)
from app.schemas.doctor_brief import (
    DoctorBriefSchema,
    ExtractedClinicalFact,
    PatientReportedSection,
    SourceReference,
    SourceType,
    ReviewStatus,
)
from app.schemas.consultation import (
    ConsultationCreate,
    ConsultationResponse,
    FollowUpCreate,
    FollowUpResponse,
    FollowUpStatus,
)
from app.schemas.audit import AuditEventType, AuditEventCreate, AuditEventResponse

__all__ = [
    "UserRole",
    "UserProfile",
    "UserCreate",
    "PatientProfile",
    "EmergencyContact",
    "ClinicianProfile",
    "ClinicianSpecialty",
    "ClinicianAvailability",
    "ClinicianVerificationStatus",
    "RequestedUrgency",
    "CaseCreate",
    "CaseResponse",
    "StateTransitionRequest",
    "CaseAcceptRequest",
    "DocumentUploadIntentRequest",
    "DocumentUploadIntentResponse",
    "DocumentResponse",
    "validate_magic_bytes",
    "DoctorBriefSchema",
    "ExtractedClinicalFact",
    "PatientReportedSection",
    "SourceReference",
    "SourceType",
    "ReviewStatus",
    "ConsultationCreate",
    "ConsultationResponse",
    "FollowUpCreate",
    "FollowUpResponse",
    "FollowUpStatus",
    "AuditEventType",
    "AuditEventCreate",
    "AuditEventResponse",
]
