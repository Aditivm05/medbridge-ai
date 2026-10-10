from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime


class SourceType(str, Enum):
    PATIENT_INPUT = "patient_input"
    DOCUMENT = "document"


class SourceReference(BaseModel):
    sourceType: SourceType
    sourceId: str
    referenceText: str
    pageNumber: Optional[int] = None


class ExtractedClinicalFact(BaseModel):
    fact: str
    value: str
    unit: Optional[str] = Field(None, description="Clinical measurement unit, e.g. mg/dL, mmHg, °F")
    sourceDocumentId: str
    pageNumber: Optional[int] = None


class PatientReportedSection(BaseModel):
    chiefComplaint: str
    symptoms: List[str]
    timelineDuration: str
    knownMedicalConditions: List[str]
    currentMedications: List[str]
    allergies: List[str]


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REVIEWED = "reviewed"


class PatientReviewData(BaseModel):
    status: ReviewStatus = ReviewStatus.PENDING
    corrections: Optional[str] = None
    reviewedAt: Optional[datetime] = None


class ClinicianReviewData(BaseModel):
    status: ReviewStatus = ReviewStatus.PENDING
    clinicianNotes: Optional[str] = None
    reviewedAt: Optional[datetime] = None


class DoctorBriefSchema(BaseModel):
    briefId: str
    caseId: str
    schemaVersion: str = "1.0"
    isDraft: bool = True
    
    # 1. Subjective patient reported facts
    patientReported: PatientReportedSection
    
    # 2. Objective document extracted findings
    extractedFacts: List[ExtractedClinicalFact]
    
    # 3. Explicitly recorded unknowns
    unknowns: List[str] = Field(
        default_factory=list,
        description="Explicitly recorded unknown clinical parameters (e.g. unknown fasting status)"
    )
    
    # 4. Units preservation check
    unitsPreserved: bool = True
    
    # 5. Missing critical context
    missingInformation: List[str] = Field(
        default_factory=list,
        description="Gaps identified that a clinician should be aware of"
    )
    
    # 6. Suggested clinician clarification questions
    clarificationQuestions: List[str] = Field(
        default_factory=list,
        description="Suggested questions for clinician to ask patient during consultation"
    )
    
    # 7. Verifiable source references
    sources: List[SourceReference] = Field(default_factory=list)
    
    # 8. Human in the loop review gates
    patientReview: PatientReviewData = Field(default_factory=PatientReviewData)
    clinicianReview: ClinicianReviewData = Field(default_factory=ClinicianReviewData)
    
    # Disclaimer enforcement
    disclaimer: str = (
        "CONFIDENTIAL MEDICAL BRIEF FOR CARE COORDINATION ONLY. "
        "THIS BRIEF DOES NOT CONSTITUTE A MEDICAL DIAGNOSIS OR PRESCRIPTION. "
        "ALL CLINICAL DECISIONS ARE THE SOLE RESPONSIBILITY OF THE LICENSED CLINICIAN."
    )
    
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class DoctorBriefPatientUpdateRequest(BaseModel):
    corrections: Optional[str] = None
    approve: bool = True


class DoctorBriefClinicianUpdateRequest(BaseModel):
    clinicianNotes: str
