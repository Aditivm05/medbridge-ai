import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  Edit3,
  FileText,
  HelpCircle,
  AlertTriangle,
  ArrowLeft,
  Sparkles,
  Layers,
  PhoneCall,
  RefreshCw,
  FileWarning,
  Check,
  Info,
  Activity
} from 'lucide-react';
import {
  CaseData,
  LanguageCode,
  DoctorBrief,
  DoctorBriefEditRequest,
  SourcedFact,
  VitalFinding
} from '../../types';
import { getTranslation } from '../../i18n/translations';
import { SimulationBadge } from '../common/SimulationBadge';
import { api } from '../../services/api';

interface DoctorBriefReviewScreenProps {
  currentCase: CaseData;
  language: LanguageCode;
  onBack: () => void;
  onApproveAndEnqueue: () => void;
  onSaveCorrections?: (corrections: string) => void;
}

export const DoctorBriefReviewScreen: React.FC<DoctorBriefReviewScreenProps> = ({
  currentCase,
  language,
  onBack,
  onApproveAndEnqueue,
  onSaveCorrections,
}) => {
  const t = getTranslation(language);

  // Brief state held strictly in React memory (Zero localStorage / sessionStorage)
  const [brief, setBrief] = useState<DoctorBrief | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);
  const [isApproving, setIsApproving] = useState<boolean>(false);
  const [isSavingEdit, setIsSavingEdit] = useState<boolean>(false);
  const [errorNotice, setErrorNotice] = useState<string | null>(null);
  const [isUsingFallback, setIsUsingFallback] = useState<boolean>(false);

  // Human approval confirmation checkbox
  const [isConfirmedByPatient, setIsConfirmedByPatient] = useState<boolean>(false);

  // Edit Modal & Fields
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [editTimeline, setEditTimeline] = useState<string>('');
  const [editHistoryText, setEditHistoryText] = useState<string>('');
  const [editMedsText, setEditMedsText] = useState<string>('');
  const [editAllergiesText, setEditAllergiesText] = useState<string>('');
  const [editVitalsText, setEditVitalsText] = useState<string>('');

  // Fallback skeleton generator when backend AI fails or is unavailable
  const generateLocalFallbackBrief = useCallback((): DoctorBrief => {
    const now = new Date().toISOString();
    return {
      briefId: `brief_fallback_${currentCase.caseId}`,
      caseId: currentCase.caseId,
      schemaVersion: '1.0',
      version: 1,
      briefStatus: 'DRAFT_AI',
      reasonForConsultation: currentCase.chiefComplaint || 'unknown',
      timelineAndDetails: currentCase.duration
        ? `Patient reported duration: ${currentCase.duration}`
        : 'unknown',
      relevantHistory: [],
      currentMedications: [],
      patientReportedAllergies: [],
      vitals: [],
      documentFindings: [],
      conflicts: [],
      missingInformation: [
        'AI generation was unavailable; manual review mode enabled.',
        'Clinician should confirm pre-existing conditions and allergies directly.',
      ],
      clarificationQuestions: [
        'Have symptoms intensified or changed in character?',
        'Are you currently taking any over-the-counter or prescribed treatments?',
      ],
      sourceReferences: [
        {
          sourceType: 'PATIENT_REPORTED',
          reference: 'intake:chiefComplaint',
        },
      ],
      validationWarnings: ['Manual entry fallback active due to AI generation failure.'],
      disclaimer:
        'CONFIDENTIAL MEDICAL BRIEF FOR CARE COORDINATION ONLY. ' +
        'THIS BRIEF DOES NOT CONSTITUTE A MEDICAL DIAGNOSIS OR PRESCRIPTION. ' +
        'ALL CLINICAL DECISIONS REMAIN THE SOLE RESPONSIBILITY OF THE LICENSED CLINICIAN.',
      createdAt: now,
      updatedAt: now,
    };
  }, [currentCase]);

  // Load or generate Doctor Brief from real backend API
  const loadOrGenerateBrief = useCallback(async () => {
    setIsLoading(true);
    setErrorNotice(null);

    try {
      // 1. Try to fetch existing brief
      try {
        const existing = await api.getBrief(currentCase.caseId);
        setBrief(existing);
        setIsUsingFallback(false);
        setIsLoading(false);
        return;
      } catch (getErr: any) {
        // If 404, we proceed to generate; otherwise continue
      }

      // 2. Generate brief via real Gemini endpoint
      const generated = await api.generateBrief(currentCase.caseId, false);
      setBrief(generated);
      setIsUsingFallback(false);
    } catch (err: any) {
      console.warn('Real backend brief generation failed, enabling manual-entry fallback:', err);
      const fallback = generateLocalFallbackBrief();
      setBrief(fallback);
      setIsUsingFallback(true);
      setErrorNotice(
        err?.message ||
        'AI brief synthesis is temporarily unavailable. A manual review skeleton has been prepared so you can proceed without delay.'
      );
    } finally {
      setIsLoading(false);
    }
  }, [currentCase.caseId, generateLocalFallbackBrief]);

  useEffect(() => {
    loadOrGenerateBrief();
  }, [loadOrGenerateBrief]);

  // Handle regeneration request
  const handleRegenerate = async () => {
    setIsRegenerating(true);
    setErrorNotice(null);
    try {
      const regenerated = await api.generateBrief(currentCase.caseId, true);
      setBrief(regenerated);
      setIsUsingFallback(false);
      setIsConfirmedByPatient(false);
    } catch (err: any) {
      setErrorNotice(err?.message || 'Failed to regenerate brief.');
    } finally {
      setIsRegenerating(false);
    }
  };

  // Open Edit Modal with current values
  const handleOpenEditModal = () => {
    if (!brief) return;
    setEditTimeline(brief.timelineAndDetails || '');
    setEditHistoryText(brief.relevantHistory.map(h => h.fact).join('\n'));
    setEditMedsText(brief.currentMedications.map(m => m.fact).join('\n'));
    setEditAllergiesText(brief.patientReportedAllergies.map(a => a.fact).join('\n'));
    setEditVitalsText(brief.vitals.map(v => `${v.name}: ${v.value} ${v.unit}`).join('\n'));
    setIsEditModalOpen(true);
  };

  // Save Human Edits via PUT /cases/{case_id}/brief
  const handleSaveEdits = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!brief) return;

    setIsSavingEdit(true);
    setErrorNotice(null);

    const relevantHistory: SourcedFact[] = editHistoryText
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
      .map(f => ({
        fact: f,
        source: 'PATIENT_REPORTED',
        reference: 'patient:manual_correction',
      }));

    const currentMedications: SourcedFact[] = editMedsText
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
      .map(m => ({
        fact: m,
        source: 'PATIENT_REPORTED',
        reference: 'patient:manual_correction',
      }));

    const patientReportedAllergies: SourcedFact[] = editAllergiesText
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
      .map(a => ({
        fact: a,
        source: 'PATIENT_REPORTED',
        reference: 'patient:manual_correction',
      }));

    const vitals: VitalFinding[] = editVitalsText
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
      .map(line => {
        const parts = line.split(':');
        const name = parts[0]?.trim() || 'vital';
        const rest = parts[1]?.trim() || '';
        const spaceIdx = rest.indexOf(' ');
        const value = spaceIdx > -1 ? rest.substring(0, spaceIdx) : rest || 'unknown';
        const unit = spaceIdx > -1 ? rest.substring(spaceIdx + 1) : '';
        return {
          name,
          value,
          unit,
          source: 'PATIENT_PROVIDED',
          reference: 'patient:manual_correction',
        };
      });

    const editPayload: DoctorBriefEditRequest = {
      timelineAndDetails: editTimeline.trim() || 'unknown',
      relevantHistory,
      currentMedications,
      patientReportedAllergies,
      vitals,
    };

    try {
      if (!isUsingFallback) {
        const updated = await api.updateBrief(currentCase.caseId, editPayload);
        setBrief(updated);
      } else {
        // Fallback update in React memory
        setBrief(prev => {
          if (!prev) return null;
          return {
            ...prev,
            timelineAndDetails: editPayload.timelineAndDetails,
            relevantHistory: editPayload.relevantHistory || [],
            currentMedications: editPayload.currentMedications || [],
            patientReportedAllergies: editPayload.patientReportedAllergies || [],
            vitals: editPayload.vitals || [],
            briefStatus: 'EDITED',
            version: prev.version + 1,
            updatedAt: new Date().toISOString(),
          };
        });
      }

      // Any edit to an approved brief reverts patient approval
      setIsConfirmedByPatient(false);
      setIsEditModalOpen(false);

      if (onSaveCorrections) {
        onSaveCorrections(`Timeline: ${editTimeline}; Meds: ${editMedsText}`);
      }
    } catch (err: any) {
      setErrorNotice(err?.message || 'Could not save brief modifications.');
    } finally {
      setIsSavingEdit(false);
    }
  };

  // Approve Brief via POST /cases/{case_id}/brief/approve
  const handleApproveBrief = async () => {
    if (!brief) return;
    setIsApproving(true);
    setErrorNotice(null);

    try {
      if (!isUsingFallback) {
        const approved = await api.approveBrief(currentCase.caseId, 'Patient confirmed facts are accurate');
        setBrief(approved);
      } else {
        setBrief(prev => {
          if (!prev) return null;
          return {
            ...prev,
            briefStatus: 'PATIENT_APPROVED',
            approvedAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          };
        });
      }
      setIsConfirmedByPatient(true);
    } catch (err: any) {
      setErrorNotice(err?.message || 'Failed to record brief approval.');
    } finally {
      setIsApproving(false);
    }
  };

  // Helper to test if a string represents an explicit unknown
  const isUnknownValue = (val?: string | null): boolean => {
    if (!val) return true;
    const lower = val.trim().toLowerCase();
    return lower === 'unknown' || lower === 'unreported' || lower === 'none reported';
  };

  // Render "unknown" badge cleanly
  const renderUnknownBadge = () => (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-900 border border-amber-300"
      aria-label="Value unknown or unrecorded"
    >
      <HelpCircle className="w-3 h-3 text-amber-700" />
      unknown
    </span>
  );

  // Status badge helper
  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'PATIENT_APPROVED':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            Approved by Patient
          </span>
        );
      case 'EDITED':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-blue-100 text-blue-800 border border-blue-300">
            <Edit3 className="w-3.5 h-3.5 text-blue-600" />
            Modified — Approval Required
          </span>
        );
      case 'CLINICIAN_REVIEWED':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-purple-100 text-purple-800 border border-purple-300">
            <Check className="w-3.5 h-3.5 text-purple-600" />
            Clinician Reviewed
          </span>
        );
      case 'DRAFT_AI':
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 border border-amber-300">
            <Sparkles className="w-3.5 h-3.5 text-amber-600" />
            Draft (AI-Generated — Pending Review)
          </span>
        );
    }
  };

  const isApproved = brief?.briefStatus === 'PATIENT_APPROVED';
  const canSubmit = isApproved;

  return (
    <div className="space-y-6 max-w-4xl mx-auto px-3 sm:px-6 py-4">

      {/* 1. ZERO-NETWORK STATIC EMERGENCY PROTOCOL (India 112) - NEVER WAITS FOR BRIEF GENERATION */}
      <aside
        role="region"
        aria-label="Immediate Emergency Warning"
        className="bg-red-600 text-white rounded-2xl p-4 sm:p-5 shadow-lg border border-red-700"
      >
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-red-700 shrink-0">
              <PhoneCall className="w-5 h-5 text-white" aria-hidden="true" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-wider bg-white/20 px-2 py-0.5 rounded">
                  Static Zero-Network Safety Protocol
                </span>
                <span className="text-[10px] font-mono text-red-100">India 112</span>
              </div>
              <h1 className="text-sm sm:text-base font-black tracking-tight mt-0.5">
                IMMEDIATE EMERGENCY WARNING
              </h1>
              <p className="text-xs text-red-100 leading-relaxed mt-1">
                If experiencing severe chest pressure, acute difficulty breathing, loss of consciousness,
                or uncontrolled bleeding, immediately dial <strong>112</strong> or go to the nearest hospital.
                Do not wait for online brief review.
              </p>
            </div>
          </div>
          <a
            href="tel:112"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-white text-red-700 hover:bg-red-50 active:scale-95 text-xs font-black shadow transition-all shrink-0 cursor-pointer"
            aria-label="Call India National Emergency Services at 112"
          >
            <PhoneCall className="w-4 h-4 text-red-700" aria-hidden="true" />
            <span>Call 112 (Emergency)</span>
          </a>
        </div>
      </aside>

      {/* 2. PERMANENT SAFETY BANNER (Non-negotiable requirement) */}
      <div
        role="alert"
        aria-live="polite"
        className="bg-amber-50 border-2 border-amber-400 rounded-2xl p-4 sm:p-5 shadow-xs flex items-start gap-3 text-amber-950"
      >
        <ShieldAlert className="w-6 h-6 text-amber-700 shrink-0 mt-0.5" aria-hidden="true" />
        <div className="text-xs sm:text-sm leading-relaxed">
          <strong className="block font-black uppercase tracking-wide text-amber-900 mb-1">
            AI-generated summary of what you provided. Not a diagnosis or medical advice. Review and correct before submitting.
          </strong>
          <p className="text-amber-800 text-xs">
            {brief?.disclaimer ||
              'CONFIDENTIAL MEDICAL BRIEF FOR CARE COORDINATION ONLY. THIS BRIEF DOES NOT CONSTITUTE A MEDICAL DIAGNOSIS OR PRESCRIPTION. ALL CLINICAL DECISIONS REMAIN THE SOLE RESPONSIBILITY OF THE LICENSED CLINICIAN.'}
          </p>
        </div>
      </div>

      {/* Error notification if backend AI synthesis failed */}
      {errorNotice && (
        <div
          role="alert"
          className="bg-rose-50 border border-rose-300 rounded-xl p-4 flex items-start gap-3 text-rose-950 text-xs"
        >
          <FileWarning className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <strong className="block font-bold text-rose-900 mb-0.5">
              Generation Notice
            </strong>
            <p className="leading-relaxed">{errorNotice}</p>
          </div>
          <button
            type="button"
            onClick={handleRegenerate}
            disabled={isRegenerating}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-100 hover:bg-rose-200 text-rose-800 font-bold text-xs transition cursor-pointer"
            aria-label="Retry AI Doctor Brief generation"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRegenerating ? 'animate-spin' : ''}`} />
            <span>Retry</span>
          </button>
        </div>
      )}

      {/* Loading State Spinner */}
      {isLoading && (
        <div
          role="status"
          aria-live="polite"
          className="bg-white rounded-2xl p-10 text-center border border-slate-200 shadow-xs"
        >
          <div className="w-10 h-10 border-4 border-brand-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <h2 className="text-base font-black text-slate-800">
            Synthesizing Doctor Brief with Gemini...
          </h2>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            Extracting objective lab findings from documents, assembling timeline facts, and checking for clinical discrepancies.
          </p>
        </div>
      )}

      {/* Main Review Card */}
      {!isLoading && brief && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4 sm:p-7 shadow-xs space-y-6">

          {/* Top Header Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onBack}
                className="p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 cursor-pointer focus:ring-2 focus:ring-brand-500 focus:outline-hidden"
                aria-label="Go back to previous screen"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg sm:text-2xl font-black text-slate-900 tracking-tight">
                    {t.briefReviewTitle}
                  </h2>
                  <span className="text-[11px] font-mono font-bold bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                    v{brief.version}.0
                  </span>
                  {renderStatusBadge(brief.briefStatus)}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Review the structured summary extracted from your intake and medical attachments.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 self-start sm:self-center">
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={isRegenerating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-xs font-bold text-slate-700 transition cursor-pointer disabled:opacity-50"
                aria-label="Regenerate brief with AI"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isRegenerating ? 'animate-spin' : ''}`} />
                <span>Regenerate</span>
              </button>
              <SimulationBadge />
            </div>
          </div>

          {/* Validation Warnings (if any) */}
          {brief.validationWarnings && brief.validationWarnings.length > 0 && (
            <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-3 text-xs text-amber-900 space-y-1">
              <strong className="block font-bold">Synthesis Advisory:</strong>
              <ul className="list-disc pl-4 space-y-0.5">
                {brief.validationWarnings.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* SECTION 1: Patient-Reported Facts */}
          <section
            aria-labelledby="section-patient-reported"
            className="rounded-xl border border-slate-200 overflow-hidden"
          >
            <div className="bg-blue-50/80 px-4 py-2.5 border-b border-blue-200 flex flex-wrap items-center justify-between gap-2">
              <h3
                id="section-patient-reported"
                className="text-xs font-black uppercase tracking-wider text-blue-950 flex items-center gap-1.5"
              >
                <FileText className="w-4 h-4 text-blue-600" aria-hidden="true" />
                1. Patient-Reported Facts
              </h3>
              <span className="text-[10px] font-bold bg-blue-200 text-blue-900 px-2 py-0.5 rounded uppercase">
                Source: PATIENT_REPORTED
              </span>
            </div>

            <div className="p-4 space-y-4 text-xs text-slate-700 bg-white">
              {/* Reason for Consultation */}
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-black text-slate-900 uppercase text-[11px] tracking-wider">
                    Reason for Consultation (Chief Complaint):
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">intake:chiefComplaint</span>
                </div>
                <p className="mt-1 p-2.5 bg-slate-50 rounded-lg text-slate-800 font-medium leading-relaxed">
                  {brief.reasonForConsultation || renderUnknownBadge()}
                </p>
              </div>

              {/* Timeline & Details */}
              <div className="pt-2 border-t border-slate-100">
                <div className="flex items-center justify-between">
                  <span className="font-black text-slate-900 uppercase text-[11px] tracking-wider">
                    Timeline and Symptom Details:
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">intake:timeline</span>
                </div>
                <div className="mt-1 p-2.5 bg-slate-50 rounded-lg text-slate-800 leading-relaxed">
                  {isUnknownValue(brief.timelineAndDetails) ? renderUnknownBadge() : brief.timelineAndDetails}
                </div>
              </div>

              {/* Grid: Medical History, Medications, Allergies */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-100">
                {/* Past Medical History */}
                <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/50 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">Medical History</span>
                    <span className="text-[9px] font-bold bg-blue-100 text-blue-800 px-1.5 py-0.2 rounded">
                      PATIENT_REPORTED
                    </span>
                  </div>
                  {brief.relevantHistory.length === 0 ? (
                    <div className="text-slate-400 italic">None reported / {renderUnknownBadge()}</div>
                  ) : (
                    <ul className="space-y-1">
                      {brief.relevantHistory.map((fact, idx) => (
                        <li key={idx} className="flex items-start gap-1.5 text-slate-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0 mt-1.5" />
                          <span>{fact.fact}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Current Medications */}
                <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/50 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">Current Medications</span>
                    <span className="text-[9px] font-bold bg-blue-100 text-blue-800 px-1.5 py-0.2 rounded">
                      PATIENT_REPORTED
                    </span>
                  </div>
                  {brief.currentMedications.length === 0 ? (
                    <div className="text-slate-400 italic">None reported / {renderUnknownBadge()}</div>
                  ) : (
                    <ul className="space-y-1">
                      {brief.currentMedications.map((med, idx) => (
                        <li key={idx} className="flex items-start gap-1.5 text-slate-700">
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0 mt-1.5" />
                          <span>{med.fact}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Allergies */}
                <div className="p-3 rounded-lg border border-slate-100 bg-slate-50/50 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">Allergies</span>
                    <span className="text-[9px] font-bold bg-rose-100 text-rose-800 px-1.5 py-0.2 rounded">
                      PATIENT_REPORTED
                    </span>
                  </div>
                  {brief.patientReportedAllergies.length === 0 ? (
                    <div className="text-slate-400 italic">None reported / {renderUnknownBadge()}</div>
                  ) : (
                    <ul className="space-y-1">
                      {brief.patientReportedAllergies.map((alg, idx) => (
                        <li key={idx} className="flex items-start gap-1.5 text-rose-800 font-semibold">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0 mt-1.5" />
                          <span>{alg.fact}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              {/* Vitals (if recorded) */}
              <div className="pt-2 border-t border-slate-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-black text-slate-900 uppercase text-[11px] tracking-wider flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-blue-600" />
                    Recorded Vital Signs
                  </span>
                  <span className="text-[10px] font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                    Source: PATIENT_PROVIDED
                  </span>
                </div>

                {brief.vitals.length === 0 ? (
                  <p className="text-slate-400 italic">No vitals provided in intake / {renderUnknownBadge()}</p>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {brief.vitals.map((v, idx) => (
                      <div key={idx} className="p-2.5 rounded-lg border border-slate-200 bg-slate-50 text-center">
                        <span className="text-[10px] uppercase font-bold text-slate-500 block">
                          {v.name}
                        </span>
                        <div className="font-mono font-black text-sm text-slate-900 mt-0.5">
                          {isUnknownValue(v.value) ? renderUnknownBadge() : `${v.value} ${v.unit !== 'unknown' ? v.unit : ''}`}
                        </div>
                        <span className="text-[9px] text-slate-400 block mt-0.5 font-mono">
                          {v.reference}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

            </div>
          </section>

          {/* SECTION 2: Document-Extracted Facts */}
          <section
            aria-labelledby="section-document-extracted"
            className="rounded-xl border border-teal-200 overflow-hidden"
          >
            <div className="bg-teal-50 px-4 py-2.5 border-b border-teal-200 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-teal-700" aria-hidden="true" />
                <h3
                  id="section-document-extracted"
                  className="text-xs font-black uppercase tracking-wider text-teal-950"
                >
                  2. Document-Extracted Clinical Facts
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-teal-900 bg-teal-200 px-2 py-0.5 rounded">
                  Units & References Preserved Exactly
                </span>
              </div>
            </div>

            <div className="p-4 bg-white">
              {brief.documentFindings.length === 0 ? (
                <div className="text-center py-6 text-slate-400 italic text-xs">
                  <p>No objective lab findings or document text extracted.</p>
                  <span className="text-[11px] text-slate-500 block mt-1">
                    (Attach synthetic blood reports or scan images on the upload screen to extract objective findings).
                  </span>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left border-collapse" role="table">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 font-bold uppercase text-[10px] tracking-wider">
                        <th className="py-2.5 pr-3">Clinical Finding / Parameter</th>
                        <th className="py-2.5 px-3">Reported Value & Unit</th>
                        <th className="py-2.5 px-3">Extraction Source</th>
                        <th className="py-2.5 pl-3">Source Document & Page</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {brief.documentFindings.map((finding, idx) => (
                        <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-2.5 pr-3 font-bold text-slate-900">
                            {finding.finding}
                          </td>
                          <td className="py-2.5 px-3 font-mono font-bold text-teal-800">
                            {isUnknownValue(finding.value) ? (
                              renderUnknownBadge()
                            ) : (
                              <span>
                                {finding.value} {finding.unit && finding.unit !== 'unknown' ? finding.unit : ''}
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                                finding.extractionSource === 'PDF_TEXT'
                                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                                  : 'bg-purple-100 text-purple-800 border border-purple-200'
                              }`}
                            >
                              {finding.extractionSource}
                            </span>
                          </td>
                          <td className="py-2.5 pl-3 text-slate-600 font-mono text-[11px]">
                            <div className="flex items-center gap-1.5">
                              <span className="font-semibold text-slate-800 truncate max-w-[140px]">
                                {finding.documentId}
                              </span>
                              <span className="bg-slate-100 text-slate-600 px-1.5 py-0.2 rounded text-[10px]">
                                p.{finding.pageNumber || 1}
                              </span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>

          {/* SECTION 3: Clinical Conflicts (Side-by-side, Never Resolved) */}
          {brief.conflicts.length > 0 && (
            <section
              aria-labelledby="section-conflicts"
              className="rounded-xl border-2 border-rose-400 bg-rose-50/40 p-4 sm:p-5"
            >
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0" aria-hidden="true" />
                <div>
                  <h3
                    id="section-conflicts"
                    className="text-xs sm:text-sm font-black uppercase tracking-wider text-rose-950"
                  >
                    Identified Clinical Discrepancies (Side-by-Side — Unresolved)
                  </h3>
                  <p className="text-[11px] text-rose-800 mt-0.5">
                    Discrepancies identified between patient statements and medical records. Neither is discarded or assumed; the clinician will verify directly.
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {brief.conflicts.map((conf, idx) => (
                  <div
                    key={idx}
                    className="bg-white rounded-xl border border-rose-200 p-3.5 shadow-2xs space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between pb-2 border-b border-rose-100">
                      <span className="font-black text-rose-900 text-xs">
                        Item in Conflict: {conf.item}
                      </span>
                      <span className="text-[10px] font-bold uppercase bg-rose-100 text-rose-800 px-2 py-0.5 rounded">
                        Discrepancy #{idx + 1}
                      </span>
                    </div>

                    {/* Side by side comparison */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                      <div className="p-2.5 rounded-lg bg-blue-50/70 border border-blue-200">
                        <span className="text-[10px] font-bold text-blue-900 uppercase block mb-1">
                          Source A: {conf.sourceA}
                        </span>
                        <div className="font-mono font-bold text-sm text-blue-950">
                          {conf.valueA}
                        </div>
                      </div>

                      <div className="p-2.5 rounded-lg bg-teal-50/70 border border-teal-200">
                        <span className="text-[10px] font-bold text-teal-900 uppercase block mb-1">
                          Source B: {conf.sourceB}
                        </span>
                        <div className="font-mono font-bold text-sm text-teal-950">
                          {conf.valueB}
                        </div>
                      </div>
                    </div>

                    {conf.description && (
                      <p className="text-slate-600 text-[11px] pt-1">
                        <strong>Clinical Note:</strong> {conf.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* SECTION 4 & 5: Missing Information & Clarification Questions */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

            {/* Missing Information / Context Gaps */}
            <div className="rounded-xl border border-amber-300 bg-amber-50/30 overflow-hidden">
              <div className="bg-amber-100/70 px-4 py-2 border-b border-amber-200 flex items-center gap-2">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-700" aria-hidden="true" />
                <h4 className="text-xs font-black uppercase tracking-wider text-amber-900">
                  Missing Clinical Context / Gaps
                </h4>
              </div>
              <div className="p-3.5 bg-white space-y-2 text-xs">
                {brief.missingInformation.length === 0 ? (
                  <p className="text-slate-400 italic">No critical clinical gaps recorded.</p>
                ) : (
                  brief.missingInformation.map((info, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-amber-900">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0 mt-1.5" />
                      <span className="leading-relaxed">{info}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Clarification Questions for Clinician */}
            <div className="rounded-xl border border-indigo-200 bg-indigo-50/30 overflow-hidden">
              <div className="bg-indigo-100/70 px-4 py-2 border-b border-indigo-200 flex items-center gap-2">
                <HelpCircle className="w-3.5 h-3.5 text-indigo-700" aria-hidden="true" />
                <h4 className="text-xs font-black uppercase tracking-wider text-indigo-900">
                  Suggested Clarification Questions
                </h4>
              </div>
              <div className="p-3.5 bg-white space-y-2 text-xs">
                {brief.clarificationQuestions.length === 0 ? (
                  <p className="text-slate-400 italic">No clarification questions prepared.</p>
                ) : (
                  brief.clarificationQuestions.map((q, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-indigo-950">
                      <span className="font-bold text-indigo-600 font-mono text-[11px] shrink-0">
                        Q{idx + 1}.
                      </span>
                      <span className="leading-relaxed">{q}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* SECTION 6: Verifiable Source References */}
          <div className="rounded-xl border border-slate-200 p-4 bg-slate-50/50 space-y-2">
            <h4 className="text-xs font-black uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-slate-500" aria-hidden="true" />
              Source Verification Map
            </h4>
            <div className="space-y-1.5 max-h-40 overflow-y-auto">
              {brief.sourceReferences.length === 0 ? (
                <p className="text-xs text-slate-400 italic">No source references registered.</p>
              ) : (
                brief.sourceReferences.map((ref, idx) => (
                  <div key={idx} className="text-[11px] text-slate-600 flex items-center gap-2 bg-white p-2 rounded border border-slate-100">
                    <span className="font-mono text-[9px] bg-slate-200 text-slate-800 px-1.5 py-0.5 rounded uppercase font-bold">
                      {ref.sourceType}
                    </span>
                    <span className="font-mono text-slate-700 font-semibold truncate">
                      {ref.reference}
                    </span>
                    {ref.pageNumber && (
                      <span className="text-slate-400 text-[10px]">
                        (Page {ref.pageNumber})
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* SECTION 7: Patient Approval Gate & Submission Row */}
          <div className="pt-5 border-t border-slate-200 space-y-4">

            {/* Approval Checkbox Agreement */}
            <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 space-y-3">
              <label className="flex items-start gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={isConfirmedByPatient}
                  onChange={(e) => setIsConfirmedByPatient(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500 cursor-pointer"
                  aria-describedby="approval-gate-desc"
                />
                <div className="text-xs text-slate-700">
                  <strong className="text-slate-900 block font-bold">
                    Patient Verification & Approval Confirmation
                  </strong>
                  <span id="approval-gate-desc" className="text-slate-500 leading-relaxed block mt-0.5">
                    I confirm that the reason for consultation and timeline details accurately represent my health concern.
                    I understand this summary is solely for care coordination and does not replace in-person medical evaluation.
                  </span>
                </div>
              </label>

              {/* Status Action Banner */}
              {!isApproved ? (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-slate-200">
                  <div className="flex items-center gap-2 text-xs text-amber-800 font-medium">
                    <Info className="w-4 h-4 text-amber-600 shrink-0" />
                    <span>Click <strong>&quot;Approve Brief&quot;</strong> to authorize submission to the doctor matching pool.</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleApproveBrief}
                    disabled={!isConfirmedByPatient || isApproving}
                    className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-xs shadow-xs transition cursor-pointer"
                    aria-label="Approve Doctor Brief"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    <span>{isApproving ? 'Approving...' : 'Approve Brief'}</span>
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-xs text-emerald-800 font-bold bg-emerald-50 p-2.5 rounded-lg border border-emerald-200">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Brief approved by patient on {new Date(brief.approvedAt || brief.updatedAt).toLocaleTimeString()}. Ready to submit.</span>
                </div>
              )}
            </div>

            {/* Primary Action Buttons */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
              <button
                type="button"
                onClick={handleOpenEditModal}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-slate-300 hover:bg-slate-100 text-xs font-bold text-slate-700 transition cursor-pointer focus:ring-2 focus:ring-brand-500"
                aria-label="Suggest corrections or edit brief details"
              >
                <Edit3 className="w-3.5 h-3.5 text-slate-600" />
                <span>{t.suggestEditBtn}</span>
              </button>

              <div className="w-full sm:w-auto flex flex-col sm:flex-row items-center gap-2">
                {!canSubmit && (
                  <span className="text-[11px] text-amber-700 font-semibold text-center sm:text-right">
                    Review and approve above to enable submission
                  </span>
                )}
                <button
                  type="button"
                  onClick={onApproveAndEnqueue}
                  disabled={!canSubmit}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-bold text-sm shadow-md transition-all cursor-pointer focus:ring-2 focus:ring-brand-500"
                  aria-label="Submit Doctor Brief to clinician matching pool"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Submit to Clinician Matching Pool</span>
                </button>
              </div>
            </div>

          </div>
        </div>
      )}

      {/* Suggest Edit / Human Correction Modal */}
      {isEditModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-modal-title"
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-3 sm:p-4 overflow-y-auto"
        >
          <div className="bg-white rounded-2xl max-w-lg w-full p-5 sm:p-6 shadow-2xl border border-slate-200 space-y-4 my-8">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 id="edit-modal-title" className="text-base font-black text-slate-900">
                {t.editModalTitle}
              </h3>
              <span className="text-[10px] font-bold uppercase bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                Human Correction
              </span>
            </div>

            <p className="text-xs text-slate-500 leading-relaxed">
              Correct any details in your reported symptoms, medical history, or current medications.
              <strong> Saving changes will revert approval and require you to re-approve the brief.</strong>
            </p>

            <form onSubmit={handleSaveEdits} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-bold text-slate-800 mb-1">
                  Timeline and Symptom Details:
                </label>
                <textarea
                  rows={3}
                  value={editTimeline}
                  onChange={(e) => setEditTimeline(e.target.value)}
                  placeholder="e.g. Fever started 48 hours ago instead of 36 hours; nausea started after food."
                  className="w-full p-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 outline-hidden font-sans"
                  required
                />
              </div>

              <div>
                <label className="block font-bold text-slate-800 mb-1">
                  Past Medical History (one per line):
                </label>
                <textarea
                  rows={2}
                  value={editHistoryText}
                  onChange={(e) => setEditHistoryText(e.target.value)}
                  placeholder="e.g. Hypertension (controlled)"
                  className="w-full p-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 outline-hidden font-sans"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-800 mb-1">
                  Current Medications (one per line):
                </label>
                <textarea
                  rows={2}
                  value={editMedsText}
                  onChange={(e) => setEditMedsText(e.target.value)}
                  placeholder="e.g. Amlodipine 5mg OD"
                  className="w-full p-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 outline-hidden font-sans"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-800 mb-1">
                  Allergies (one per line):
                </label>
                <input
                  type="text"
                  value={editAllergiesText}
                  onChange={(e) => setEditAllergiesText(e.target.value)}
                  placeholder="e.g. Penicillin (mild cutaneous rash)"
                  className="w-full p-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 outline-hidden font-sans"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-800 mb-1">
                  Vitals (e.g. Blood Pressure: 120/80 mmHg):
                </label>
                <input
                  type="text"
                  value={editVitalsText}
                  onChange={(e) => setEditVitalsText(e.target.value)}
                  placeholder="e.g. Blood Pressure: 120/80 mmHg"
                  className="w-full p-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 outline-hidden font-sans"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  className="px-3 py-2 rounded-xl text-slate-600 hover:text-slate-800 text-xs font-bold transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSavingEdit}
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs shadow-xs transition cursor-pointer disabled:opacity-50"
                >
                  {isSavingEdit ? 'Saving...' : 'Save & Revert to Draft'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};
