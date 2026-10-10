from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

DISCLAIMER = (
    "CONFIDENTIAL MEDICAL BRIEF FOR CARE COORDINATION ONLY. "
    "THIS BRIEF DOES NOT CONSTITUTE A MEDICAL DIAGNOSIS OR PRESCRIPTION. "
    "ALL CLINICAL DECISIONS REMAIN THE SOLE RESPONSIBILITY OF THE LICENSED CLINICIAN."
)


class BriefStatus(str, Enum):
    DRAFT_AI = "DRAFT_AI"
    PATIENT_APPROVED = "PATIENT_APPROVED"
    CLINICIAN_REVIEWED = "CLINICIAN_REVIEWED"
    EDITED = "EDITED"


class FactSource(str, Enum):
    PATIENT_REPORTED = "PATIENT_REPORTED"
    DOCUMENT_EXTRACTED = "DOCUMENT_EXTRACTED"


class VitalSource(str, Enum):
    PATIENT_PROVIDED = "PATIENT_PROVIDED"
    DEVICE_PROVIDED = "DEVICE_PROVIDED"


class ExtractionSource(str, Enum):
    PDF_TEXT = "PDF_TEXT"
    AI_EXTRACTED = "AI_EXTRACTED"


class SourceReference(BaseModel):
    sourceType: FactSource
    reference: str = Field(..., description="e.g. 'chiefComplaint', 'intake:medications', or 'doc_123:page_1'")
    documentId: Optional[str] = Field(None, description="Document ID if from document")
    pageNumber: Optional[int] = Field(None, description="1-indexed page number if from document")

    model_config = ConfigDict(extra="forbid")


class SourcedFact(BaseModel):
    fact: str = Field(..., description="Objective statement of reported or extracted fact")
    source: FactSource = Field(..., description="PATIENT_REPORTED or DOCUMENT_EXTRACTED")
    reference: str = Field(..., description="Field name or document ID and page number")

    model_config = ConfigDict(extra="forbid")


class VitalFinding(BaseModel):
    name: str = Field(..., description="Name of vital sign, e.g. blood pressure, heart rate, temperature")
    value: str = Field(..., description="Measurement value or 'unknown'")
    unit: str = Field(..., description="Exact measurement unit, e.g. mmHg, bpm, °F, % or 'unknown'")
    source: VitalSource = Field(VitalSource.PATIENT_PROVIDED, description="PATIENT_PROVIDED or DEVICE_PROVIDED")
    reference: str = Field(..., description="Field name or document reference")

    model_config = ConfigDict(extra="forbid")


class DocumentFinding(BaseModel):
    documentId: str = Field(..., description="ID of the source document")
    pageNumber: int = Field(..., description="1-indexed page number where finding was extracted")
    extractionSource: ExtractionSource = Field(..., description="PDF_TEXT or AI_EXTRACTED")
    finding: str = Field(..., description="Clinical finding, observation, or test result")
    value: Optional[str] = Field(None, description="Reported value or 'unknown'")
    unit: Optional[str] = Field(None, description="Measurement unit preserved exactly, or 'unknown'")
    reference: str = Field(..., description="e.g. doc_id:page_1")

    model_config = ConfigDict(extra="forbid")


class ClinicalConflict(BaseModel):
    item: str = Field(..., description="The clinical parameter in conflict, e.g. Metformin dosage")
    valueA: str = Field(..., description="First reported or extracted value")
    sourceA: str = Field(..., description="Source of first value, e.g. PATIENT_REPORTED (intake form)")
    valueB: str = Field(..., description="Second reported or extracted value")
    sourceB: str = Field(..., description="Source of second value, e.g. DOCUMENT_EXTRACTED (doc_123 page 1)")
    description: Optional[str] = Field(None, description="Neutral description of the discrepancy")

    model_config = ConfigDict(extra="forbid")


class GeminiDoctorBriefOutput(BaseModel):
    """
    Strict schema sent to Gemini for structured JSON generation.
    Excludes server-managed fields (caseId, briefId, briefStatus, schemaVersion, disclaimer).
    Notice: Strictly forbids any diagnosis, prescription, or treatment plan fields.
    """
    timelineAndDetails: Optional[str] = Field("unknown", description="Timeline of symptoms and relevant details")
    relevantHistory: List[SourcedFact] = Field(default_factory=list, description="Relevant medical history with sources")
    currentMedications: List[SourcedFact] = Field(default_factory=list, description="Current medications with sources and exact units")
    patientReportedAllergies: List[SourcedFact] = Field(default_factory=list, description="Patient reported allergies with sources")
    vitals: List[VitalFinding] = Field(default_factory=list, description="Vitals with exact units and sources")
    documentFindings: List[DocumentFinding] = Field(default_factory=list, description="Key document findings with documentId, pageNumber and extractionSource")
    conflicts: List[ClinicalConflict] = Field(default_factory=list, description="Discrepancies identified between sources without resolving them")
    missingInformation: List[str] = Field(default_factory=list, description="Gaps or missing critical clinical parameters")
    clarificationQuestions: List[str] = Field(default_factory=list, description="Suggested clarification questions for clinician to ask patient")
    sourceReferences: List[SourceReference] = Field(default_factory=list, description="Verifiable references for facts")

    model_config = ConfigDict(extra="forbid")


class DoctorBrief(BaseModel):
    """
    Server-side DoctorBrief model stored in Firestore.
    Contains full versioning, lifecycle status, human edits, and audit references.
    """
    briefId: str
    caseId: str
    schemaVersion: str = "1.0"
    version: int = 1
    briefStatus: BriefStatus = BriefStatus.DRAFT_AI
    reasonForConsultation: str = Field(..., description="Patient's own words unchanged from chiefComplaint")
    timelineAndDetails: Optional[str] = "unknown"
    relevantHistory: List[SourcedFact] = Field(default_factory=list)
    currentMedications: List[SourcedFact] = Field(default_factory=list)
    patientReportedAllergies: List[SourcedFact] = Field(default_factory=list)
    vitals: List[VitalFinding] = Field(default_factory=list)
    documentFindings: List[DocumentFinding] = Field(default_factory=list)
    conflicts: List[ClinicalConflict] = Field(default_factory=list)
    missingInformation: List[str] = Field(default_factory=list)
    clarificationQuestions: List[str] = Field(default_factory=list)
    sourceReferences: List[SourceReference] = Field(default_factory=list)
    validationWarnings: List[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    lastEditedBy: Optional[str] = None
    lastEditedAt: Optional[datetime] = None
    approvedBy: Optional[str] = None
    approvedAt: Optional[datetime] = None
    reviewedBy: Optional[str] = None
    reviewedAt: Optional[datetime] = None
    previousVersions: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DoctorBriefGenerateRequest(BaseModel):
    confirmRegenerate: bool = Field(False, description="Must be true if regenerating over a human-edited brief")


class DoctorBriefEditRequest(BaseModel):
    timelineAndDetails: Optional[str] = None
    relevantHistory: Optional[List[SourcedFact]] = None
    currentMedications: Optional[List[SourcedFact]] = None
    patientReportedAllergies: Optional[List[SourcedFact]] = None
    vitals: Optional[List[VitalFinding]] = None
    documentFindings: Optional[List[DocumentFinding]] = None
    conflicts: Optional[List[ClinicalConflict]] = None
    missingInformation: Optional[List[str]] = None
    clarificationQuestions: Optional[List[str]] = None
    sourceReferences: Optional[List[SourceReference]] = None


class DoctorBriefPatientApproveRequest(BaseModel):
    notes: Optional[str] = None


class DoctorBriefClinicianReviewRequest(BaseModel):
    clinicianNotes: Optional[str] = None


def create_blank_brief_skeleton(
    case_id: str,
    reason_for_consultation: str,
    validation_warnings: Optional[List[str]] = None,
) -> DoctorBrief:
    """Creates a blank DoctorBrief skeleton for manual entry upon generation failure."""
    now = datetime.utcnow()
    return DoctorBrief(
        briefId=f"brief_{uuid.uuid4().hex[:12]}",
        caseId=case_id,
        schemaVersion="1.0",
        version=1,
        briefStatus=BriefStatus.DRAFT_AI,
        reasonForConsultation=reason_for_consultation or "unknown",
        timelineAndDetails="unknown",
        relevantHistory=[],
        currentMedications=[],
        patientReportedAllergies=[],
        vitals=[],
        documentFindings=[],
        conflicts=[],
        missingInformation=["AI brief generation unavailable or failed; manual clinical entry required."],
        clarificationQuestions=[],
        sourceReferences=[
            SourceReference(
                sourceType=FactSource.PATIENT_REPORTED,
                reference="chiefComplaint",
            )
        ],
        validationWarnings=validation_warnings or [],
        disclaimer=DISCLAIMER,
        createdAt=now,
        updatedAt=now,
        previousVersions=[],
    )


# Compatibility aliases for legacy schemas
DoctorBriefSchema = DoctorBrief
ReviewStatus = BriefStatus
SourceType = FactSource
ExtractedClinicalFact = DocumentFinding
class PatientReportedSection(BaseModel):
    chiefComplaint: str
    symptoms: List[str] = []
    timelineDuration: str = "unknown"
    knownMedicalConditions: List[str] = []
    currentMedications: List[str] = []
    allergies: List[str] = []

