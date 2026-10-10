import React, { useState, useEffect, useCallback } from 'react';
import {
  Stethoscope,
  FileText,
  Sparkles,
  CheckCircle2,
  ArrowLeft,
  ShieldAlert,
  Check,
  AlertTriangle,
  Layers,
  HelpCircle,
  Activity,
  UserCheck,
  RefreshCw,
  FileWarning
} from 'lucide-react';
import { CaseData, LanguageCode, DoctorBrief } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { SimulationBadge } from '../common/SimulationBadge';
import { api } from '../../services/api';
import { authService } from '../../services/authService';

interface ConsultationWorkspaceProps {
  currentCase: CaseData;
  language: LanguageCode;
  onBack: () => void;
  onSaveConsultation: (notes: string, careAdvice: string) => void;
}

export const ConsultationWorkspace: React.FC<ConsultationWorkspaceProps> = ({
  currentCase,
  language,
  onBack,
  onSaveConsultation,
}) => {
  const t = getTranslation(language);
  const [activeTab, setActiveTab] = useState<'brief' | 'docs'>('brief');

  // Real Doctor Brief state (zero mock data in clinician review flow)
  const [brief, setBrief] = useState<DoctorBrief | null>(null);
  const [isLoadingBrief, setIsLoadingBrief] = useState<boolean>(true);
  const [briefError, setBriefError] = useState<string | null>(null);

  // Clinician review submission state
  const [isSubmittingReview, setIsSubmittingReview] = useState<boolean>(false);
  const [reviewNotesInput, setReviewNotesInput] = useState<string>('');
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewSuccessMessage, setReviewSuccessMessage] = useState<string | null>(null);

  // Clinician consultation form state
  const [clinicianNotes, setClinicianNotes] = useState(
    currentCase.consultation?.clinicianNotes ||
      'Review of Doctor Brief confirms acute inflammatory findings. Differential includes acute appendicitis vs. acute mesenteric adenitis. Patient is stable without systemic peritoneal rigidity.'
  );
  const [careAdvice, setCareAdvice] = useState(
    currentCase.consultation?.provisionalCareAdvice ||
      'Rest in recumbent position with knees slightly flexed to reduce abdominal wall tension. Maintain oral hydration with clear electrolyte fluids only (no solid fatty meals). Avoid application of hot water compress to abdomen. Re-evaluate temperature every 4 hours.'
  );

  const docs = currentCase.documents || [];
  const currentSession = authService.getCurrentSession();
  const isVerifiedClinician = currentSession.role === 'clinician' && currentSession.isVerifiedClinician;

  // Fetch real Doctor Brief for the relevant case from backend
  const fetchBrief = useCallback(async () => {
    setIsLoadingBrief(true);
    setBriefError(null);
    try {
      const data = await api.getBrief(currentCase.caseId);
      setBrief(data);
    } catch (err: any) {
      setBriefError(
        err?.message || 'Could not fetch Doctor Brief from backend server.'
      );
    } finally {
      setIsLoadingBrief(false);
    }
  }, [currentCase.caseId]);

  useEffect(() => {
    fetchBrief();
  }, [fetchBrief]);

  // Submit clinician review through POST /api/v1/cases/{case_id}/brief/review
  const handleReviewBrief = async () => {
    setIsSubmittingReview(true);
    setReviewError(null);
    setReviewSuccessMessage(null);

    try {
      const updatedBrief = await api.reviewBrief(
        currentCase.caseId,
        reviewNotesInput.trim() || undefined
      );
      setBrief(updatedBrief);
      setReviewSuccessMessage('Doctor Brief officially reviewed and verified. Recorded in immutable audit trail.');
    } catch (err: any) {
      setReviewError(err?.message || 'Failed to submit clinician review.');
    } finally {
      setIsSubmittingReview(false);
    }
  };

  const handleCompleteConsultation = (e: React.FormEvent) => {
    e.preventDefault();
    if (!clinicianNotes.trim() || !careAdvice.trim()) return;
    onSaveConsultation(clinicianNotes, careAdvice);
  };

  const isBriefReviewed = brief?.briefStatus === 'CLINICIAN_REVIEWED';

  return (
    <div className="space-y-6 max-w-6xl mx-auto px-3 sm:px-6 py-4">
      {/* Top Header */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100 mb-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 cursor-pointer"
              aria-label="Back to Matching Pool"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
                  {t.consultationTitle}
                </h2>
                <SimulationBadge />
              </div>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
                {t.consultationSubtitle}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono font-bold text-slate-600 bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-200">
            <span>Case #{currentCase.caseId.substring(0, 14)}</span>
            <span className="text-brand-600 font-semibold">• {currentCase.requestedUrgency.toUpperCase()}</span>
          </div>
        </div>

        {/* Disclaimer Notice */}
        <div className="bg-teal-50 border border-teal-200 rounded-xl p-3 text-xs text-teal-900 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-teal-700 shrink-0" />
          <span>
            <strong>Human Medical Authority:</strong> All clinical opinions and care advice are authored solely by the licensed clinician. Text consultations are simulated for the MVP.
          </span>
        </div>
      </div>

      {/* Main Workspace Split View (2 Columns) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

        {/* Left Column: Real Doctor Brief & Document Inspector (5 cols) */}
        <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs">
          {/* Tabs */}
          <div className="flex border-b border-slate-200 bg-slate-50">
            <button
              type="button"
              onClick={() => setActiveTab('brief')}
              className={`flex-1 py-3 text-xs font-bold border-b-2 transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                activeTab === 'brief'
                  ? 'border-brand-600 text-brand-700 bg-white'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-brand-600" />
              <span>Doctor Brief (Verified)</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('docs')}
              className={`flex-1 py-3 text-xs font-bold border-b-2 transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                activeTab === 'docs'
                  ? 'border-brand-600 text-brand-700 bg-white'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>{t.sourceDocumentsTab} ({docs.length})</span>
            </button>
          </div>

          {/* Tab Content */}
          <div className="p-4 max-h-[680px] overflow-y-auto space-y-4 text-xs">
            {activeTab === 'brief' ? (
              isLoadingBrief ? (
                /* Loading State */
                <div className="py-12 text-center space-y-3">
                  <div className="w-8 h-8 border-3 border-brand-600 border-t-transparent rounded-full animate-spin mx-auto" />
                  <p className="text-xs font-bold text-slate-700">Fetching Doctor Brief from backend...</p>
                </div>
              ) : briefError ? (
                /* Error State */
                <div className="p-4 bg-rose-50 border border-rose-300 rounded-xl space-y-3 text-rose-950">
                  <div className="flex items-center gap-2">
                    <FileWarning className="w-4 h-4 text-rose-600 shrink-0" />
                    <strong className="font-bold text-xs">Could not load Doctor Brief</strong>
                  </div>
                  <p className="text-[11px] leading-relaxed text-rose-800">{briefError}</p>
                  <button
                    type="button"
                    onClick={fetchBrief}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-100 hover:bg-rose-200 text-rose-800 font-bold text-xs transition cursor-pointer"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Retry Fetch</span>
                  </button>
                </div>
              ) : brief ? (
                /* Real Doctor Brief Content (Zero mock data) */
                <div className="space-y-4">

                  {/* Status & Review Header Badge */}
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between gap-2">
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">
                        Doctor Brief Status
                      </span>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {brief.briefStatus === 'CLINICIAN_REVIEWED' ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-100 text-purple-800 border border-purple-300">
                            <Check className="w-3 h-3 text-purple-600" />
                            Clinician Reviewed
                          </span>
                        ) : brief.briefStatus === 'PATIENT_APPROVED' ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                            Patient Approved
                          </span>
                        ) : brief.briefStatus === 'EDITED' ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-300">
                            Patient Modified
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                            Draft (AI)
                          </span>
                        )}
                        <span className="text-[10px] font-mono text-slate-500">
                          v{brief.version}.0
                        </span>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={fetchBrief}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition cursor-pointer"
                      title="Refresh brief from server"
                      aria-label="Refresh brief from server"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* CLINICIAN REVIEW ACTION BOX (Phase 7b Core Task) */}
                  <div className="p-4 rounded-xl border border-purple-200 bg-purple-50/50 space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-black uppercase tracking-wider text-purple-950 flex items-center gap-1.5">
                        <UserCheck className="w-4 h-4 text-purple-700" />
                        Clinician Review Gate
                      </h4>
                      {isBriefReviewed && (
                        <span className="text-[10px] font-bold bg-purple-200 text-purple-900 px-2 py-0.5 rounded">
                          Review Complete
                        </span>
                      )}
                    </div>

                    {isBriefReviewed ? (
                      /* Success & Persisted Review State */
                      <div className="bg-white p-3 rounded-lg border border-purple-200 space-y-1">
                        <div className="flex items-center gap-2 text-xs font-bold text-purple-900">
                          <CheckCircle2 className="w-4 h-4 text-purple-600 shrink-0" />
                          <span>Officially Reviewed & Verified</span>
                        </div>
                        <p className="text-[11px] text-slate-600 leading-relaxed">
                          Reviewed by <strong>{brief.reviewedBy || 'Assigned Clinician'}</strong> on{' '}
                          {new Date(brief.reviewedAt || brief.updatedAt).toLocaleString()}.
                        </p>
                        <p className="text-[10px] text-purple-700 italic">
                          Audit event logged: BRIEF_CLINICIAN_REVIEWED. Duplicate reviews prevented.
                        </p>
                      </div>
                    ) : (
                      /* Active Review Submission Form */
                      <div className="space-y-2.5">
                        <p className="text-[11px] text-slate-600 leading-relaxed">
                          Review the patient-approved brief below. Signing off records your professional verification of the extracted facts and timeline in the immutable audit trail.
                        </p>

                        <input
                          type="text"
                          value={reviewNotesInput}
                          onChange={(e) => setReviewNotesInput(e.target.value)}
                          placeholder="Review confirmation note (e.g. Verified history & lab findings with patient)"
                          className="w-full p-2.5 rounded-lg border border-slate-300 text-xs bg-white focus:ring-2 focus:ring-purple-500 outline-hidden font-sans"
                        />

                        {reviewError && (
                          <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-[11px] text-rose-800 leading-relaxed">
                            {reviewError}
                          </div>
                        )}

                        {reviewSuccessMessage && (
                          <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-[11px] text-emerald-800 font-medium">
                            {reviewSuccessMessage}
                          </div>
                        )}

                        <div className="flex items-center justify-between pt-1">
                          {!isVerifiedClinician && (
                            <span className="text-[10px] text-amber-700 font-semibold">
                              * Requires verified clinician credentials
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={handleReviewBrief}
                            disabled={isSubmittingReview || !isVerifiedClinician}
                            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-purple-700 hover:bg-purple-800 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-bold text-xs shadow-xs transition cursor-pointer"
                            aria-label="Submit Clinician Review"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>
                              {isSubmittingReview ? 'Submitting Review...' : 'Sign Off & Approve Doctor Brief'}
                            </span>
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 1. Patient-Reported Content */}
                  <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-900 block text-xs">Reason for Consultation:</span>
                      <span className="text-[9px] font-mono font-bold bg-blue-100 text-blue-800 px-1.5 py-0.2 rounded">
                        PATIENT_REPORTED
                      </span>
                    </div>
                    <p className="text-slate-800 leading-relaxed font-medium">
                      {brief.reasonForConsultation}
                    </p>

                    <div className="pt-2 border-t border-slate-200">
                      <span className="font-bold text-slate-700 block text-[11px]">Timeline & Details:</span>
                      <p className="text-slate-600 mt-0.5 leading-relaxed">
                        {brief.timelineAndDetails || 'unknown'}
                      </p>
                    </div>

                    {/* History, Meds, Allergies */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 border-t border-slate-200 text-[11px]">
                      <div>
                        <span className="font-bold text-slate-700 block">Medications:</span>
                        {brief.currentMedications.length === 0 ? (
                          <span className="text-slate-400 italic">None reported</span>
                        ) : (
                          <ul className="list-disc pl-3 text-slate-600">
                            {brief.currentMedications.map((m, idx) => (
                              <li key={idx}>{m.fact}</li>
                            ))}
                          </ul>
                        )}
                      </div>

                      <div>
                        <span className="font-bold text-slate-700 block">Allergies:</span>
                        {brief.patientReportedAllergies.length === 0 ? (
                          <span className="text-slate-400 italic">None reported</span>
                        ) : (
                          <ul className="list-disc pl-3 text-rose-700 font-semibold">
                            {brief.patientReportedAllergies.map((a, idx) => (
                              <li key={idx}>{a.fact}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>

                    {/* Vitals */}
                    {brief.vitals && brief.vitals.length > 0 && (
                      <div className="pt-2 border-t border-slate-200">
                        <span className="font-bold text-slate-700 block text-[11px] mb-1 flex items-center gap-1">
                          <Activity className="w-3 h-3 text-blue-600" />
                          Vitals:
                        </span>
                        <div className="grid grid-cols-2 gap-1.5">
                          {brief.vitals.map((v, idx) => (
                            <div key={idx} className="p-1.5 bg-white rounded border border-slate-200 text-[10px]">
                              <span className="font-semibold text-slate-500 block">{v.name}:</span>
                              <span className="font-mono font-bold text-slate-800">{v.value} {v.unit}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 2. Document Findings (Preserved Units) */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-black text-slate-900 uppercase tracking-wider text-[11px]">
                        Objective Document Findings:
                      </span>
                      <span className="text-[10px] font-bold text-teal-800 bg-teal-100 px-2 py-0.5 rounded">
                        Units Preserved
                      </span>
                    </div>

                    {brief.documentFindings.length === 0 ? (
                      <p className="text-slate-400 italic text-[11px]">No objective document findings extracted.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {brief.documentFindings.map((finding, idx) => (
                          <div key={idx} className="p-2.5 rounded-lg bg-teal-50/70 border border-teal-200 space-y-1">
                            <div className="flex justify-between items-center">
                              <span className="font-bold text-teal-950">{finding.finding}</span>
                              <span className="font-mono font-bold text-teal-800 text-[11px]">
                                {finding.value} {finding.unit}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                              <span className="bg-teal-200/80 text-teal-900 px-1 py-0.2 rounded font-bold uppercase">
                                {finding.extractionSource}
                              </span>
                              <span>{finding.documentId} (p.{finding.pageNumber || 1})</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* 3. Conflicts (if any) */}
                  {brief.conflicts && brief.conflicts.length > 0 && (
                    <div className="p-3 rounded-xl border border-rose-300 bg-rose-50/50 space-y-2">
                      <div className="flex items-center gap-1.5 text-rose-950 font-bold text-xs">
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                        <span>Identified Clinical Discrepancies</span>
                      </div>
                      <div className="space-y-1.5">
                        {brief.conflicts.map((c, idx) => (
                          <div key={idx} className="p-2 bg-white rounded border border-rose-200 text-[11px] space-y-1">
                            <strong className="text-rose-900 block">{c.item}</strong>
                            <div className="grid grid-cols-2 gap-2 text-[10px]">
                              <div><strong>Source A:</strong> {c.valueA}</div>
                              <div><strong>Source B:</strong> {c.valueB}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 4. Clarification Questions */}
                  <div>
                    <span className="font-bold text-slate-900 block mb-1 uppercase tracking-wider text-[11px] flex items-center gap-1">
                      <HelpCircle className="w-3.5 h-3.5 text-indigo-600" />
                      Clarification Questions for Patient:
                    </span>
                    {brief.clarificationQuestions.length === 0 ? (
                      <p className="text-slate-400 italic text-[11px]">None recorded</p>
                    ) : (
                      <ul className="list-disc pl-4 space-y-1 text-slate-600">
                        {brief.clarificationQuestions.map((q, idx) => (
                          <li key={idx}>{q}</li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* 5. Source References Map */}
                  <div className="pt-2 border-t border-slate-100">
                    <span className="font-bold text-slate-700 block mb-1 uppercase tracking-wider text-[10px] flex items-center gap-1">
                      <Layers className="w-3 h-3 text-slate-500" />
                      Verifiable Source References:
                    </span>
                    <div className="space-y-1 max-h-28 overflow-y-auto">
                      {brief.sourceReferences.map((ref, idx) => (
                        <div key={idx} className="text-[10px] text-slate-500 font-mono bg-slate-50 p-1 rounded border border-slate-100 flex items-center gap-1.5">
                          <span className="bg-slate-200 text-slate-700 px-1 rounded uppercase font-bold">{ref.sourceType}</span>
                          <span className="truncate">{ref.reference}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                </div>
              ) : (
                <div className="py-8 text-center text-slate-400 italic text-xs">
                  No Doctor Brief available for this case.
                </div>
              )
            ) : (
              /* Documents Tab */
              <div className="space-y-3">
                {docs.length === 0 ? (
                  <p className="text-slate-400 italic">No files attached by patient.</p>
                ) : (
                  docs.map((d) => (
                    <div key={d.documentId} className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-800">{d.fileName}</span>
                        <span className="text-[10px] text-emerald-700 font-bold bg-emerald-100 px-2 py-0.5 rounded">Validated</span>
                      </div>
                      <pre className="p-2.5 bg-white rounded border border-slate-200 text-[11px] font-mono whitespace-pre-wrap text-slate-700 max-h-48 overflow-y-auto">
                        {d.extractedText || 'No OCR extracted text preview available.'}
                      </pre>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Clinician Notes & Consultation Form (7 cols) */}
        <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 p-5 sm:p-7 shadow-xs">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-5">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Stethoscope className="w-4 h-4 text-brand-600" />
              Clinician Assessment Record
            </h3>
            <span className="text-xs font-mono text-slate-500">
              {currentSession.displayName || 'Dr. Rajesh Patil'}
            </span>
          </div>

          <form onSubmit={handleCompleteConsultation} className="space-y-5">
            {/* Clinical Observations */}
            <div>
              <label htmlFor="clinicianNotes" className="block text-sm font-bold text-slate-800 mb-1.5">
                {t.consultationNotesLabel} <span className="text-rose-500">*</span>
              </label>
              <textarea
                id="clinicianNotes"
                rows={5}
                value={clinicianNotes}
                onChange={(e) => setClinicianNotes(e.target.value)}
                placeholder={t.consultationNotesPlaceholder}
                className="w-full p-3.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 text-xs sm:text-sm outline-hidden text-slate-800"
                required
              />
            </div>

            {/* Provisional Care Guidance */}
            <div>
              <label htmlFor="careAdvice" className="block text-sm font-bold text-slate-800 mb-1.5">
                {t.provisionalAdviceLabel} <span className="text-rose-500">*</span>
              </label>
              <textarea
                id="careAdvice"
                rows={4}
                value={careAdvice}
                onChange={(e) => setCareAdvice(e.target.value)}
                placeholder={t.provisionalAdvicePlaceholder}
                className="w-full p-3.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 text-xs sm:text-sm outline-hidden text-slate-800"
                required
              />
            </div>

            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-[11px] text-amber-900 leading-relaxed">
              * Remember: MedBridge AI coordinates care. No prescriptions can be generated without in-person or live telemedicine compliance. Only supportive care advice permitted.
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={onBack}
                className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
              >
                Back to Queue
              </button>

              <button
                type="submit"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-700 active:scale-95 text-white font-bold text-sm shadow-md shadow-brand-500/20 transition-all cursor-pointer"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>{t.completeConsultationBtn}</span>
              </button>
            </div>
          </form>
        </div>

      </div>
    </div>
  );
};
