from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import uuid
import re

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


def _parse_metadata_sourced_facts(raw_val: Any, field_name: str) -> List[SourcedFact]:
    facts: List[SourcedFact] = []
    if not raw_val:
        return facts
    if isinstance(raw_val, list):
        for item in raw_val:
            s_item = str(item).strip()
            if s_item:
                facts.append(
                    SourcedFact(
                        fact=s_item,
                        source=FactSource.PATIENT_REPORTED,
                        reference=f"intake:{field_name}",
                    )
                )
    elif isinstance(raw_val, str):
        lines = [line.strip() for line in raw_val.replace(";", "\n").split("\n") if line.strip()]
        for line in lines:
            facts.append(
                SourcedFact(
                    fact=line,
                    source=FactSource.PATIENT_REPORTED,
                    reference=f"intake:{field_name}",
                )
            )
    return facts


def _split_vital_val_and_unit(raw_val: Any) -> Tuple[str, str]:
    """
    Takes the leading numeric part (including leading minus/plus, thousands commas,
    '/' and decimals) as the value and the rest of the string, unchanged, as the unit.
    If the text after the leading number contains a digit or is longer than 12 characters,
    keeps the whole original string as the value and sets unit to 'unknown'.
    If there is no rest, unit is 'unknown'. Non-numeric strings (e.g. 'normal') return (s, 'unknown').
    Never guesses or converts units.
    """
    if raw_val is None:
        return ("unknown", "unknown")
    s = str(raw_val).strip()
    if not s:
        return ("unknown", "unknown")

    match = re.match(r"^([-+]?[0-9][0-9.,/]*[0-9]|[-+]?[0-9])\s*(.*)$", s)
    if match:
        val = match.group(1).strip()
        rest = match.group(2).strip()
        if not rest:
            return (val if val else "unknown", "unknown")
        if any(c.isdigit() for c in rest) or len(rest) > 12:
            return (s, "unknown")
        return (val if val else "unknown", rest)

    return (s, "unknown")


def _parse_metadata_vitals(raw_vitals: Any) -> List[VitalFinding]:
    findings: List[VitalFinding] = []
    if not raw_vitals:
        return findings

    if isinstance(raw_vitals, dict):
        for k, v in raw_vitals.items():
            name = str(k).strip()
            val, unit = _split_vital_val_and_unit(v)
            findings.append(
                VitalFinding(
                    name=name,
                    value=val,
                    unit=unit,
                    source=VitalSource.PATIENT_PROVIDED,
                    reference="intake:vitals",
                )
            )
    elif isinstance(raw_vitals, list):
        for item in raw_vitals:
            if isinstance(item, dict):
                findings.extend(_parse_metadata_vitals(item))
            elif isinstance(item, str):
                findings.extend(_parse_metadata_vitals(item))
    elif isinstance(raw_vitals, str):
        # Split on semicolons, newlines, or commas that are delimiters (not thousands commas between digits)
        chunks = [c.strip() for c in re.split(r"[;\n]|,\s+|(?<=\D),|,(?=\D)", raw_vitals) if c.strip()]
        for chunk in chunks:
            if ":" in chunk:
                name_part, val_part = chunk.split(":", 1)
                name = name_part.strip()
                val, unit = _split_vital_val_and_unit(val_part)
                findings.append(
                    VitalFinding(
                        name=name,
                        value=val,
                        unit=unit,
                        source=VitalSource.PATIENT_PROVIDED,
                        reference="intake:vitals",
                    )
                )
            else:
                val, unit = _split_vital_val_and_unit(chunk)
                findings.append(
                    VitalFinding(
                        name="vital",
                        value=val,
                        unit=unit,
                        source=VitalSource.PATIENT_PROVIDED,
                        reference="intake:vitals",
                    )
                )
    return findings


def create_blank_brief_skeleton(
    case_id: str,
    reason_for_consultation: str,
    validation_warnings: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> DoctorBrief:
    """
    Creates a DoctorBrief skeleton for manual entry upon generation failure.
    Pre-fills the patient's own entered history, medications, allergies (labelled PATIENT_REPORTED)
    and vitals (labelled PATIENT_PROVIDED with reference 'intake:vitals') from case metadata.
    Leaves everything else unknown.
    """
    now = datetime.utcnow()
    meta = metadata or {}

    history_val = meta.get("knownConditions") or meta.get("history")
    relevant_history = _parse_metadata_sourced_facts(history_val, "knownConditions")
    medications = _parse_metadata_sourced_facts(meta.get("medications"), "medications")
    allergies = _parse_metadata_sourced_facts(meta.get("allergies"), "allergies")
    vitals = _parse_metadata_vitals(meta.get("vitals"))

    source_refs = [
        SourceReference(
            sourceType=FactSource.PATIENT_REPORTED,
            reference="chiefComplaint",
        )
    ]
    if relevant_history:
        source_refs.append(
            SourceReference(
                sourceType=FactSource.PATIENT_REPORTED,
                reference="intake:knownConditions",
            )
        )
    if medications:
        source_refs.append(
            SourceReference(
                sourceType=FactSource.PATIENT_REPORTED,
                reference="intake:medications",
            )
        )
    if allergies:
        source_refs.append(
            SourceReference(
                sourceType=FactSource.PATIENT_REPORTED,
                reference="intake:allergies",
            )
        )
    if vitals:
        source_refs.append(
            SourceReference(
                sourceType=FactSource.PATIENT_REPORTED,
                reference="intake:vitals",
            )
        )

    return DoctorBrief(
        briefId=f"brief_{uuid.uuid4().hex[:12]}",
        caseId=case_id,
        schemaVersion="1.0",
        version=1,
        briefStatus=BriefStatus.DRAFT_AI,
        reasonForConsultation=reason_for_consultation or "unknown",
        timelineAndDetails="unknown",
        relevantHistory=relevant_history,
        currentMedications=medications,
        patientReportedAllergies=allergies,
        vitals=vitals,
        documentFindings=[],
        conflicts=[],
        missingInformation=["AI brief generation unavailable or failed; manual clinical entry required."],
        clarificationQuestions=[],
        sourceReferences=source_refs,
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

