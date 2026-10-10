import { useState, useEffect } from 'react';
import { CaseData, DoctorBriefData, DocumentData, FollowUpData, ScreenView } from '../types';
import { initialMockCases, mockClinicians, sampleDoctorBrief } from './mockData';

class CaseStore {
  private cases: CaseData[] = [...initialMockCases];
  private activeCaseId: string | null = initialMockCases[0].caseId;
  private currentScreen: ScreenView = 'patient-dashboard';
  private listeners: Set<() => void> = new Set();

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn());
  }

  public getCases(): CaseData[] {
    return [...this.cases];
  }

  public getActiveCase(): CaseData | null {
    if (!this.activeCaseId) return null;
    return this.cases.find((c) => c.caseId === this.activeCaseId) || null;
  }

  public setActiveCaseId(id: string | null): void {
    this.activeCaseId = id;
    this.notify();
  }

  public getCurrentScreen(): ScreenView {
    return this.currentScreen;
  }

  public navigateTo(screen: ScreenView, caseId?: string): void {
    this.currentScreen = screen;
    if (caseId) {
      this.activeCaseId = caseId;
    }
    this.notify();
  }

  public createCase(data: {
    chiefComplaint: string;
    duration: string;
    requestedUrgency: 'routine' | 'urgent' | 'emergency';
    patientLanguage: 'en' | 'hi' | 'mr';
    symptoms?: string[];
  }): CaseData {
    const caseId = `case_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const idempotencyKey = `idem_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const now = new Date().toISOString();

    const newCase: CaseData = {
      caseId,
      patientId: 'patient_current_user',
      assignedClinicianId: null,
      assignedClinicianName: null,
      requestedUrgency: data.requestedUrgency,
      status: 'DRAFT',
      idempotencyKey,
      chiefComplaint: data.chiefComplaint,
      duration: data.duration,
      patientLanguage: data.patientLanguage,
      documentCount: 0,
      doctorBriefId: null,
      doctorBrief: null,
      documents: [],
      consultationId: null,
      consultation: null,
      followUp: null,
      createdAt: now,
      updatedAt: now,
    };

    this.cases = [newCase, ...this.cases];
    this.activeCaseId = caseId;
    this.notify();
    return newCase;
  }

  public attachDocument(caseId: string, doc: DocumentData): void {
    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        const existingDocs = c.documents || [];
        const updatedDocs = [...existingDocs, doc];
        return {
          ...c,
          documentCount: updatedDocs.length,
          documents: updatedDocs,
          updatedAt: new Date().toISOString(),
        };
      }
      return c;
    });
    this.notify();
  }

  public generateDoctorBrief(caseId: string): DoctorBriefData {
    const targetCase = this.cases.find((c) => c.caseId === caseId);
    const now = new Date().toISOString();

    const brief: DoctorBriefData = {
      ...sampleDoctorBrief,
      briefId: `brief_${caseId}`,
      caseId,
      patientReported: {
        chiefComplaint: targetCase?.chiefComplaint || sampleDoctorBrief.patientReported.chiefComplaint,
        symptoms: [targetCase?.chiefComplaint || 'Reported symptoms', 'Pain / Discomfort'],
        timelineDuration: targetCase?.duration || '48 hours',
        knownMedicalConditions: ['No chronic conditions specified'],
        currentMedications: ['None currently reported'],
        allergies: ['No known drug allergies reported'],
      },
      patientReview: {
        status: 'pending',
        corrections: null,
        reviewedAt: null,
      },
      createdAt: now,
      updatedAt: now,
    };

    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          status: 'SUBMITTED',
          submittedAt: now,
          doctorBriefId: brief.briefId,
          doctorBrief: brief,
          updatedAt: now,
        };
      }
      return c;
    });

    this.notify();
    return brief;
  }

  public patientReviewBrief(caseId: string, approve: boolean, corrections?: string): void {
    const now = new Date().toISOString();
    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId && c.doctorBrief) {
        const updatedBrief: DoctorBriefData = {
          ...c.doctorBrief,
          patientReview: {
            status: approve ? 'approved' : 'edited',
            corrections: corrections || null,
            reviewedAt: now,
          },
          updatedAt: now,
        };

        return {
          ...c,
          status: 'MATCHING', // Enqueued into matching pool upon approval
          doctorBrief: updatedBrief,
          updatedAt: now,
        };
      }
      return c;
    });
    this.notify();
  }

  public claimCaseAtomic(
    caseId: string,
    clinicianId: string,
    simulateConflict: boolean = false
  ): { success: boolean; error?: string } {
    const targetCase = this.cases.find((c) => c.caseId === caseId);
    if (!targetCase) return { success: false, error: 'Case not found' };

    if (simulateConflict || targetCase.status !== 'MATCHING' || targetCase.assignedClinicianId) {
      return {
        success: false,
        error: `HTTP 409 Conflict: Case '${caseId}' has already been claimed by another clinician. Matching queue updated.`,
      };
    }

    const clinician = mockClinicians.find((doc) => doc.clinicianId === clinicianId) || mockClinicians[0];
    const now = new Date().toISOString();

    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          status: 'ACCEPTED',
          assignedClinicianId: clinician.clinicianId,
          assignedClinicianName: clinician.fullName,
          acceptedAt: now,
          updatedAt: now,
        };
      }
      return c;
    });

    this.notify();
    return { success: true };
  }

  public recordConsultationNotes(
    caseId: string,
    notes: string,
    careAdvice: string
  ): void {
    const now = new Date().toISOString();

    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          status: 'IN_CONSULTATION',
          consultation: {
            consultationId: `consult_${caseId}`,
            caseId,
            clinicianId: c.assignedClinicianId || 'demo_doc_patil',
            clinicianName: c.assignedClinicianName || 'Dr. Rajesh Patil [DEMO / SIMULATED]',
            consultationType: 'text_based_consultation_simulated',
            isSimulated: true,
            clinicianNotes: notes,
            provisionalCareAdvice: careAdvice,
            startedAt: c.acceptedAt || now,
            endedAt: null,
          },
          updatedAt: now,
        };
      }
      return c;
    });

    this.notify();
  }

  public completeCaseAndFollowUp(
    caseId: string,
    followUp: { required: boolean; recommendedDate: string; instructions: string }
  ): void {
    const now = new Date().toISOString();

    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        const followUpData: FollowUpData = {
          followUpId: `followup_${caseId}`,
          caseId,
          patientId: c.patientId,
          clinicianId: c.assignedClinicianId || 'demo_doc_patil',
          required: followUp.required,
          recommendedDate: followUp.recommendedDate,
          status: 'scheduled',
          instructions: followUp.instructions,
          createdAt: now,
        };

        return {
          ...c,
          status: 'COMPLETED',
          completedAt: now,
          followUp: followUpData,
          consultation: c.consultation
            ? { ...c.consultation, endedAt: now }
            : null,
          updatedAt: now,
        };
      }
      return c;
    });

    this.notify();
  }

  public resetToSyntheticDefaults(): void {
    this.cases = [...initialMockCases];
    this.activeCaseId = initialMockCases[0].caseId;
    this.currentScreen = 'patient-dashboard';
    this.notify();
  }
}

export const caseStore = new CaseStore();

export function useCaseStore() {
  const [, setTick] = useState(0);

  useEffect(() => {
    return caseStore.subscribe(() => setTick((t) => t + 1));
  }, []);

  return {
    cases: caseStore.getCases(),
    activeCase: caseStore.getActiveCase(),
    currentScreen: caseStore.getCurrentScreen(),
    navigateTo: (screen: ScreenView, caseId?: string) => caseStore.navigateTo(screen, caseId),
    setActiveCaseId: (id: string | null) => caseStore.setActiveCaseId(id),
    createCase: (data: any) => caseStore.createCase(data),
    attachDocument: (caseId: string, doc: DocumentData) => caseStore.attachDocument(caseId, doc),
    generateDoctorBrief: (caseId: string) => caseStore.generateDoctorBrief(caseId),
    patientReviewBrief: (caseId: string, approve: boolean, corrections?: string) =>
      caseStore.patientReviewBrief(caseId, approve, corrections),
    claimCaseAtomic: (caseId: string, clinicianId: string, simulateConflict?: boolean) =>
      caseStore.claimCaseAtomic(caseId, clinicianId, simulateConflict),
    recordConsultationNotes: (caseId: string, notes: string, careAdvice: string) =>
      caseStore.recordConsultationNotes(caseId, notes, careAdvice),
    completeCaseAndFollowUp: (caseId: string, followUp: any) =>
      caseStore.completeCaseAndFollowUp(caseId, followUp),
    resetToSyntheticDefaults: () => caseStore.resetToSyntheticDefaults(),
  };
}
