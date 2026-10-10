export type UserRole = 'patient' | 'clinician' | 'admin';

export type LanguageCode = 'en' | 'hi' | 'mr';

export type RequestedUrgency = 'routine' | 'urgent' | 'emergency';

export type CaseStatus =
  | 'DRAFT'
  | 'SUBMITTED'
  | 'MATCHING'
  | 'ACCEPTED'
  | 'IN_CONSULTATION'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'NO_CLINICIAN_AVAILABLE'
  | 'FAILED'
  | 'ESCALATED';

export type ScreenView =
  | 'patient-dashboard'
  | 'intake'
  | 'upload'
  | 'brief-review'
  | 'clinician-dashboard'
  | 'consultation'
  | 'follow-up'
  | 'audit';

export interface UserProfile {
  userId: string;
  email: string;
  displayName: string;
  role: UserRole;
  phone?: string;
}

export interface ExtractedClinicalFact {
  fact: string;
  value: string;
  unit?: string | null;
  sourceDocumentId: string;
  pageNumber?: number | null;
}

export interface SourceReference {
  sourceType: 'patient_input' | 'document';
  sourceId: string;
  referenceText: string;
  pageNumber?: number | null;
}

export interface PatientReportedData {
  chiefComplaint: string;
  symptoms: string[];
  timelineDuration: string;
  knownMedicalConditions: string[];
  currentMedications: string[];
  allergies: string[];
}

export interface DoctorBriefData {
  briefId: string;
  caseId: string;
  schemaVersion: string;
  isDraft: boolean;
  patientReported: PatientReportedData;
  extractedFacts: ExtractedClinicalFact[];
  unknowns: string[];
  unitsPreserved: boolean;
  missingInformation: string[];
  clarificationQuestions: string[];
  sources: SourceReference[];
  patientReview: {
    status: 'pending' | 'approved' | 'edited';
    corrections?: string | null;
    reviewedAt?: string | null;
  };
  clinicianReview: {
    status: 'pending' | 'reviewed';
    clinicianNotes?: string | null;
    reviewedAt?: string | null;
  };
  disclaimer: string;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentData {
  documentId: string;
  caseId: string;
  fileName: string;
  mimeType: string;
  sizeBytes: number;
  uploadedAt: string;
  magicBytesValidated: boolean;
  ocrStatus: 'pending' | 'processed' | 'failed';
  extractedText?: string | null;
}

export interface ConsultationData {
  consultationId: string;
  caseId: string;
  clinicianId: string;
  clinicianName: string;
  consultationType: 'text_based_consultation_simulated';
  isSimulated: boolean;
  clinicianNotes: string;
  provisionalCareAdvice: string;
  startedAt: string;
  endedAt?: string | null;
}

export interface FollowUpData {
  followUpId: string;
  caseId: string;
  patientId: string;
  clinicianId: string;
  required: boolean;
  recommendedDate: string;
  status: 'scheduled' | 'completed' | 'cancelled';
  instructions: string;
  createdAt: string;
}

export interface CaseData {
  caseId: string;
  patientId: string;
  assignedClinicianId?: string | null;
  assignedClinicianName?: string | null;
  requestedUrgency: RequestedUrgency;
  status: CaseStatus;
  idempotencyKey: string;
  chiefComplaint: string;
  duration: string;
  patientLanguage: LanguageCode;
  documentCount: number;
  doctorBriefId?: string | null;
  doctorBrief?: DoctorBriefData | null;
  documents?: DocumentData[];
  consultationId?: string | null;
  consultation?: ConsultationData | null;
  followUp?: FollowUpData | null;
  createdAt: string;
  updatedAt: string;
  submittedAt?: string | null;
  acceptedAt?: string | null;
  completedAt?: string | null;
}

export interface ClinicianData {
  clinicianId: string;
  fullName: string;
  licenseNumber: string;
  specialty: string;
  languages: string[];
  verificationStatus: string;
  availability: 'available' | 'busy' | 'offline';
  isDemo: boolean;
  currentCaseId?: string | null;
}
