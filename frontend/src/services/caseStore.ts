import { useState, useEffect } from 'react';
import { CaseData, ClinicianMatchResponse, DoctorBrief, DoctorBriefData, DoctorBriefEditRequest, DocumentData, FollowUpData, ScreenView } from '../types';
import { mockClinicians } from './mockData';
import { api } from './api';

export function mapBackendCaseToCaseData(sc: any, existing?: CaseData): CaseData {
  return {
    caseId: sc.caseId,
    patientId: sc.patientId,
    assignedClinicianId: sc.assignedClinicianId ?? existing?.assignedClinicianId ?? null,
    assignedClinicianName: existing?.assignedClinicianName ?? null,
    requestedUrgency: sc.requestedUrgency,
    status: sc.status,
    idempotencyKey: sc.idempotencyKey || existing?.idempotencyKey || `idem_${sc.caseId}`,
    chiefComplaint: sc.chiefComplaint,
    duration: sc.duration,
    patientLanguage: sc.patientLanguage || 'en',
    documentCount: sc.documentCount ?? existing?.documentCount ?? 0,
    doctorBriefId: sc.doctorBriefId ?? existing?.doctorBriefId ?? null,
    doctorBrief: existing?.doctorBrief ?? null,
    realDoctorBrief: existing?.realDoctorBrief ?? null,
    documents: existing?.documents ?? [],
    consultationId: sc.consultationId ?? existing?.consultationId ?? null,
    consultation: existing?.consultation ?? null,
    followUp: existing?.followUp ?? null,
    createdAt: typeof sc.createdAt === 'string' ? sc.createdAt : new Date(sc.createdAt || Date.now()).toISOString(),
    updatedAt: typeof sc.updatedAt === 'string' ? sc.updatedAt : new Date(sc.updatedAt || Date.now()).toISOString(),
    submittedAt: sc.submittedAt
      ? typeof sc.submittedAt === 'string'
        ? sc.submittedAt
        : new Date(sc.submittedAt).toISOString()
      : existing?.submittedAt ?? null,
    acceptedAt: sc.acceptedAt
      ? typeof sc.acceptedAt === 'string'
        ? sc.acceptedAt
        : new Date(sc.acceptedAt).toISOString()
      : existing?.acceptedAt ?? null,
    completedAt: sc.completedAt
      ? typeof sc.completedAt === 'string'
        ? sc.completedAt
        : new Date(sc.completedAt).toISOString()
      : existing?.completedAt ?? null,
    metadata: sc.metadata || existing?.metadata || {},
    matchResult: sc.matchResult ?? existing?.matchResult ?? null,
  };
}

class CaseStore {
  private cases: CaseData[] = [];
  private activeCaseId: string | null = null;
  private currentScreen: ScreenView = 'patient-dashboard';
  private isLoadingPatientCases: boolean = false;
  private patientCasesError: string | null = null;
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

  public getIsLoadingPatientCases(): boolean {
    return this.isLoadingPatientCases;
  }

  public getPatientCasesError(): string | null {
    return this.patientCasesError;
  }

  public navigateTo(screen: ScreenView, caseId?: string): void {
    this.currentScreen = screen;
    if (caseId) {
      this.activeCaseId = caseId;
    }
    this.notify();
  }

  public async loadPatientCases(): Promise<CaseData[]> {
    this.isLoadingPatientCases = true;
    this.patientCasesError = null;
    this.notify();

    try {
      const serverCases = await api.listCases();
      if (!Array.isArray(serverCases)) {
        throw new Error('Invalid response format: expected list of cases');
      }

      const existingCasesMap = new Map(this.cases.map((c) => [c.caseId, c]));
      const mappedCases: CaseData[] = serverCases.map((sc: any) =>
        mapBackendCaseToCaseData(sc, existingCasesMap.get(sc.caseId))
      );

      this.cases = mappedCases;
      if (this.activeCaseId && !mappedCases.some((c) => c.caseId === this.activeCaseId)) {
        this.activeCaseId = mappedCases.length > 0 ? mappedCases[0].caseId : null;
      } else if (!this.activeCaseId && mappedCases.length > 0) {
        this.activeCaseId = mappedCases[0].caseId;
      }

      this.isLoadingPatientCases = false;
      this.patientCasesError = null;
      this.notify();
      return mappedCases;
    } catch (err: any) {
      this.isLoadingPatientCases = false;
      this.patientCasesError = err?.message || 'Failed to load cases from server';
      this.notify();
      throw err;
    }
  }

  public async createCase(data: {
    chiefComplaint: string;
    duration: string;
    requestedUrgency: 'routine' | 'urgent' | 'emergency';
    patientLanguage: 'en' | 'hi' | 'mr';
    symptoms?: string[];
    knownConditions?: string;
    medications?: string;
    allergies?: string;
    idempotencyKey?: string;
  }): Promise<CaseData> {
    const chiefComplaint = (data.chiefComplaint || '').trim();
    const duration = (data.duration || '').trim();
    if (!chiefComplaint || chiefComplaint.length < 5) {
      throw new Error('Chief complaint is required and must be at least 5 characters.');
    }
    if (!duration || duration.length < 2) {
      throw new Error('Duration is required and must be at least 2 characters.');
    }

    const idempotencyKey =
      data.idempotencyKey ||
      `idem_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

    const metadata: Record<string, any> = {};
    if (data.symptoms && Array.isArray(data.symptoms) && data.symptoms.length > 0) {
      metadata.symptoms = data.symptoms;
    }
    if (data.knownConditions && data.knownConditions.trim()) {
      metadata.knownConditions = data.knownConditions.trim();
    }
    if (data.medications && data.medications.trim()) {
      metadata.medications = data.medications.trim();
    }
    if (data.allergies && data.allergies.trim()) {
      metadata.allergies = data.allergies.trim();
    }

    const payload: any = {
      chiefComplaint,
      duration,
      requestedUrgency: data.requestedUrgency,
      patientLanguage: data.patientLanguage || 'en',
      idempotencyKey,
    };
    if (Object.keys(metadata).length > 0) {
      payload.metadata = metadata;
    }

    // Call real backend endpoint through shared API client.
    // NO silent mock fallback: throws on backend error so the caller can handle it visibly.
    const serverCase = await api.createCase(payload);

    const newCase = mapBackendCaseToCaseData(serverCase);
    this.cases = [newCase, ...this.cases.filter((c) => c.caseId !== newCase.caseId)];
    this.activeCaseId = newCase.caseId;
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

  public async generateDoctorBrief(caseId: string, confirmRegenerate: boolean = false): Promise<DoctorBrief> {
    const serverBrief = await api.generateBrief(caseId, confirmRegenerate);
    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          doctorBriefId: serverBrief.briefId,
          realDoctorBrief: serverBrief,
          updatedAt: serverBrief.updatedAt || new Date().toISOString(),
        };
      }
      return c;
    });
    this.notify();
    return serverBrief;
  }

  public async getDoctorBrief(caseId: string): Promise<DoctorBrief> {
    const serverBrief = await api.getBrief(caseId);
    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          doctorBriefId: serverBrief.briefId,
          realDoctorBrief: serverBrief,
          updatedAt: serverBrief.updatedAt || c.updatedAt,
        };
      }
      return c;
    });
    this.notify();
    return serverBrief;
  }

  public async updateDoctorBrief(
    caseId: string,
    payload: DoctorBriefEditRequest
  ): Promise<DoctorBrief> {
    const serverBrief = await api.updateBrief(caseId, payload);
    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          doctorBriefId: serverBrief.briefId,
          realDoctorBrief: serverBrief,
          updatedAt: serverBrief.updatedAt || new Date().toISOString(),
        };
      }
      return c;
    });
    this.notify();
    return serverBrief;
  }

  public async approveDoctorBrief(
    caseId: string,
    notes?: string
  ): Promise<DoctorBrief> {
    const serverBrief = await api.approveBrief(caseId, notes);
    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          doctorBriefId: serverBrief.briefId,
          realDoctorBrief: serverBrief,
          updatedAt: serverBrief.updatedAt || new Date().toISOString(),
        };
      }
      return c;
    });
    this.notify();
    return serverBrief;
  }

  public async refreshCase(caseId: string): Promise<CaseData | null> {
    try {
      const serverCase = await api.getCase(caseId);
      const existing = this.cases.find((c) => c.caseId === caseId);
      const updatedCase = mapBackendCaseToCaseData(serverCase, existing);
      this.cases = this.cases.map((c) => (c.caseId === caseId ? { ...c, ...updatedCase } : c));
      this.notify();
      return updatedCase;
    } catch {
      return null;
    }
  }

  public async submitAndMatchCase(
    caseId: string
  ): Promise<{ case: CaseData; matchResult: ClinicianMatchResponse }> {
    let targetCase = this.cases.find((c) => c.caseId === caseId);
    if (!targetCase) {
      targetCase = (await this.refreshCase(caseId)) || undefined;
    }

    // Submit case if still in DRAFT
    if (!targetCase || targetCase.status === 'DRAFT') {
      await api.submitCase(caseId, targetCase?.idempotencyKey);
    }

    // Trigger authoritative backend clinician matching
    const matchResult = await api.matchCase(caseId);

    // Refresh case from backend to sync authoritative status and metadata
    const updatedCase = await this.refreshCase(caseId);

    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          status: (matchResult.status as any) || c.status,
          matchResult,
          updatedAt: new Date().toISOString(),
        };
      }
      return c;
    });
    this.notify();

    return {
      case: updatedCase || this.cases.find((c) => c.caseId === caseId)!,
      matchResult,
    };
  }

  public async matchCase(caseId: string): Promise<ClinicianMatchResponse> {
    const matchResult = await api.matchCase(caseId);
    await this.refreshCase(caseId);
    this.cases = this.cases.map((c) => {
      if (c.caseId === caseId) {
        return {
          ...c,
          status: (matchResult.status as any) || c.status,
          matchResult,
          updatedAt: new Date().toISOString(),
        };
      }
      return c;
    });
    this.notify();
    return matchResult;
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
          status: approve ? 'MATCHING' : c.status,
          doctorBrief: updatedBrief,
          updatedAt: now,
        };
      }
      return c;
    });
    this.notify();
  }

  public async claimCaseAtomic(
    caseId: string,
    clinicianId: string,
    simulateConflict: boolean = false
  ): Promise<{ success: boolean; error?: string }> {
    if (simulateConflict) {
      return {
        success: false,
        error: `HTTP 409 Conflict: Case '${caseId}' concurrency collision detected. Another clinician accepted simultaneously.`,
      };
    }

    try {
      const serverCase = await api.acceptCase(caseId);
      const clinician = mockClinicians.find((doc) => doc.clinicianId === clinicianId) || mockClinicians[0];
      const now = new Date().toISOString();

      this.cases = this.cases.map((c) => {
        if (c.caseId === caseId) {
          return {
            ...c,
            status: 'ACCEPTED',
            assignedClinicianId: serverCase.assignedClinicianId || clinician.clinicianId,
            assignedClinicianName: clinician.fullName,
            acceptedAt: serverCase.acceptedAt || now,
            updatedAt: serverCase.updatedAt || now,
          };
        }
        return c;
      });

      this.notify();
      return { success: true };
    } catch (err: any) {
      if (err.status === 409 || err.message?.includes('409') || err.message?.includes('Conflict')) {
        return {
          success: false,
          error: `HTTP 409 Conflict: ${err.message}`,
        };
      }
      if (err.status === 403 || err.message?.includes('403') || err.message?.includes('Forbidden')) {
        return {
          success: false,
          error: `HTTP 403 Forbidden: ${err.message || 'Clinician verification required to accept cases.'}`,
        };
      }

      // Local fallback if offline/mock mode
      const targetCase = this.cases.find((c) => c.caseId === caseId);
      if (!targetCase || targetCase.status !== 'MATCHING' || targetCase.assignedClinicianId) {
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
  }

  public async declineCase(
    caseId: string,
    reason?: string
  ): Promise<{ success: boolean; error?: string }> {
    try {
      const updatedCase = await api.declineCase(caseId, reason);
      this.cases = this.cases.map((c) => {
        if (c.caseId === caseId) {
          return {
            ...c,
            status: updatedCase.status as any,
            updatedAt: updatedCase.updatedAt || new Date().toISOString(),
          };
        }
        return c;
      });
      this.notify();
      return { success: true };
    } catch {
      // Local fallback
      this.cases = this.cases.map((c) => {
        if (c.caseId === caseId) {
          return {
            ...c,
            status: 'NO_CLINICIAN_AVAILABLE',
            updatedAt: new Date().toISOString(),
          };
        }
        return c;
      });
      this.notify();
      return { success: true };
    }
  }

  public async syncMatchingPool(): Promise<void> {
    try {
      const serverPool = await api.getMatchingPool();
      if (Array.isArray(serverPool)) {
        const existingIds = new Set(this.cases.map((c) => c.caseId));
        const newCases: CaseData[] = [];

        for (const sc of serverPool) {
          if (!existingIds.has(sc.caseId)) {
            newCases.push({
              caseId: sc.caseId,
              patientId: sc.patientId,
              assignedClinicianId: sc.assignedClinicianId || null,
              assignedClinicianName: sc.assignedClinicianName || null,
              requestedUrgency: sc.requestedUrgency || 'urgent',
              status: sc.status,
              idempotencyKey: sc.idempotencyKey || `idem_${sc.caseId}`,
              chiefComplaint: sc.chiefComplaint || 'Urgent coordination case',
              duration: sc.duration || '24 hours',
              patientLanguage: sc.patientLanguage || 'en',
              documentCount: sc.documentCount || 0,
              doctorBriefId: sc.doctorBriefId || null,
              doctorBrief: null,
              documents: [],
              consultationId: null,
              consultation: null,
              followUp: null,
              createdAt: sc.createdAt || new Date().toISOString(),
              updatedAt: sc.updatedAt || new Date().toISOString(),
            });
          }
        }

        this.cases = [
          ...newCases,
          ...this.cases.map((c) => {
            const match = serverPool.find((sc) => sc.caseId === c.caseId);
            if (match) {
              return {
                ...c,
                status: match.status,
                assignedClinicianId: match.assignedClinicianId,
              };
            }
            return c;
          }),
        ];
        this.notify();
      }
    } catch {}
  }

  public async recordConsultationNotes(
    caseId: string,
    notes: string,
    careAdvice: string
  ): Promise<{ success: boolean; error?: string }> {
    const now = new Date().toISOString();

    try {
      const serverConsultation = await api.saveConsultation(caseId, {
        clinicianNotes: notes,
        provisionalCareAdvice: careAdvice,
        isSimulated: true,
      });

      this.cases = this.cases.map((c) => {
        if (c.caseId === caseId) {
          return {
            ...c,
            status: 'IN_CONSULTATION',
            consultationId: serverConsultation.consultationId,
            consultation: {
              consultationId: serverConsultation.consultationId,
              caseId,
              clinicianId: serverConsultation.clinicianId,
              clinicianName: c.assignedClinicianName || 'Dr. Rajesh Patil [DEMO / SIMULATED]',
              consultationType: 'text_based_consultation_simulated',
              isSimulated: true,
              clinicianNotes: serverConsultation.clinicianNotes,
              provisionalCareAdvice: serverConsultation.provisionalCareAdvice,
              startedAt: serverConsultation.startedAt || c.acceptedAt || now,
              endedAt: serverConsultation.endedAt || null,
            },
            updatedAt: now,
          };
        }
        return c;
      });

      this.notify();
      return { success: true };
    } catch (err: any) {
      // Local fallback for offline/synthetic state
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
      return { success: true, error: err?.message };
    }
  }

  public async completeCaseAndFollowUp(
    caseId: string,
    followUp: { required: boolean; recommendedDate: string; instructions: string }
  ): Promise<{ success: boolean; error?: string }> {
    const now = new Date().toISOString();

    try {
      const result = await api.completeCaseWithFollowUp(caseId, followUp);
      const serverCase = result.case;
      const serverFollowUp = result.followUp;

      this.cases = this.cases.map((c) => {
        if (c.caseId === caseId) {
          return {
            ...c,
            status: 'COMPLETED',
            completedAt: serverCase?.completedAt || now,
            followUp: {
              followUpId: serverFollowUp?.followUpId || `followup_${caseId}`,
              caseId,
              patientId: c.patientId,
              clinicianId: serverFollowUp?.clinicianId || c.assignedClinicianId || 'demo_doc_patil',
              required: serverFollowUp?.required ?? followUp.required,
              recommendedDate: serverFollowUp?.recommendedDate ?? followUp.recommendedDate,
              status: (serverFollowUp?.status || 'scheduled') as any,
              instructions: serverFollowUp?.instructions ?? followUp.instructions,
              createdAt: serverFollowUp?.createdAt || now,
            },
            consultation: c.consultation
              ? { ...c.consultation, endedAt: now }
              : null,
            updatedAt: now,
          };
        }
        return c;
      });

      this.notify();
      return { success: true };
    } catch (err: any) {
      // Local fallback for offline/synthetic state
      const followUpData: FollowUpData = {
        followUpId: `followup_${caseId}`,
        caseId,
        patientId: 'patient_current_user',
        clinicianId: 'demo_doc_patil',
        required: followUp.required,
        recommendedDate: followUp.recommendedDate,
        status: 'scheduled',
        instructions: followUp.instructions,
        createdAt: now,
      };

      this.cases = this.cases.map((c) => {
        if (c.caseId === caseId) {
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
      return { success: true, error: err?.message };
    }
  }

  public resetToSyntheticDefaults(): void {
    this.cases = [];
    this.activeCaseId = null;
    this.isLoadingPatientCases = false;
    this.patientCasesError = null;
    this.currentScreen = 'patient-dashboard';
    this.notify();
    this.loadPatientCases().catch(() => {});
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
    isLoadingPatientCases: caseStore.getIsLoadingPatientCases(),
    patientCasesError: caseStore.getPatientCasesError(),
    loadPatientCases: () => caseStore.loadPatientCases(),
    navigateTo: (screen: ScreenView, caseId?: string) => caseStore.navigateTo(screen, caseId),
    setActiveCaseId: (id: string | null) => caseStore.setActiveCaseId(id),
    createCase: (data: any) => caseStore.createCase(data),
    attachDocument: (caseId: string, doc: DocumentData) => caseStore.attachDocument(caseId, doc),
    generateDoctorBrief: (caseId: string, confirmRegenerate?: boolean) =>
      caseStore.generateDoctorBrief(caseId, confirmRegenerate),
    getDoctorBrief: (caseId: string) => caseStore.getDoctorBrief(caseId),
    updateDoctorBrief: (caseId: string, payload: DoctorBriefEditRequest) =>
      caseStore.updateDoctorBrief(caseId, payload),
    approveDoctorBrief: (caseId: string, notes?: string) =>
      caseStore.approveDoctorBrief(caseId, notes),
    submitAndMatchCase: (caseId: string) => caseStore.submitAndMatchCase(caseId),
    matchCase: (caseId: string) => caseStore.matchCase(caseId),
    refreshCase: (caseId: string) => caseStore.refreshCase(caseId),
    patientReviewBrief: (caseId: string, approve: boolean, corrections?: string) =>
      caseStore.patientReviewBrief(caseId, approve, corrections),
    claimCaseAtomic: (caseId: string, clinicianId: string, simulateConflict?: boolean) =>
      caseStore.claimCaseAtomic(caseId, clinicianId, simulateConflict),
    declineCase: (caseId: string, reason?: string) => caseStore.declineCase(caseId, reason),
    syncMatchingPool: () => caseStore.syncMatchingPool(),
    recordConsultationNotes: (caseId: string, notes: string, careAdvice: string) =>
      caseStore.recordConsultationNotes(caseId, notes, careAdvice),
    completeCaseAndFollowUp: (caseId: string, followUp: any) =>
      caseStore.completeCaseAndFollowUp(caseId, followUp),
    resetToSyntheticDefaults: () => caseStore.resetToSyntheticDefaults(),
  };
}
