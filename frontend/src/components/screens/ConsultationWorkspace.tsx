import React, { useState } from 'react';
import { 
  Stethoscope, 
  FileText, 
  Sparkles, 
  CheckCircle2, 
  ArrowLeft, 
  ShieldAlert 
} from 'lucide-react';
import { CaseData, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { SimulationBadge } from '../common/SimulationBadge';

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
  const [clinicianNotes, setClinicianNotes] = useState(
    currentCase.consultation?.clinicianNotes ||
      'Review of Doctor Brief confirms acute inflammatory findings (WBC 14,800 /µL, CRP 42 mg/L) with focal right lower quadrant tenderness. Differential includes acute appendicitis vs. acute mesenteric adenitis. Patient is stable without systemic peritoneal rigidity.'
  );
  const [careAdvice, setCareAdvice] = useState(
    currentCase.consultation?.provisionalCareAdvice ||
      'Rest in recumbent position with knees slightly flexed to reduce abdominal wall tension. Maintain oral hydration with clear electrolyte fluids only (no solid fatty meals). Avoid application of hot water compress to abdomen. Re-evaluate temperature every 4 hours.'
  );

  const brief = currentCase.doctorBrief;
  const docs = currentCase.documents || [];

  const handleComplete = (e: React.FormEvent) => {
    e.preventDefault();
    if (!clinicianNotes.trim() || !careAdvice.trim()) return;
    onSaveConsultation(clinicianNotes, careAdvice);
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Top Header */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100 mb-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 cursor-pointer"
              aria-label="Back"
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
        {/* Left Column: Doctor Brief & Document Inspector (5 cols) */}
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
              <Sparkles className="w-3.5 h-3.5" />
              <span>{t.briefInspectorTab}</span>
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
          <div className="p-4 max-h-[600px] overflow-y-auto space-y-4 text-xs">
            {activeTab === 'brief' ? (
              brief ? (
                <>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="font-bold text-slate-900 block mb-1">Chief Complaint:</span>
                    <p className="text-slate-700">{brief.patientReported.chiefComplaint}</p>
                    <span className="font-semibold text-slate-500 block mt-1">Timeline: {brief.patientReported.timelineDuration}</span>
                  </div>

                  <div>
                    <span className="font-bold text-slate-900 block mb-1.5 uppercase tracking-wider text-[11px]">
                      Extracted Objective Facts (Units Preserved):
                    </span>
                    <div className="space-y-1.5">
                      {brief.extractedFacts.map((fact, idx) => (
                        <div key={idx} className="p-2.5 rounded-lg bg-teal-50 border border-teal-200 flex justify-between items-center">
                          <span className="font-medium text-teal-950">{fact.fact}</span>
                          <span className="font-mono font-bold text-teal-800">{fact.value} {fact.unit}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <span className="font-bold text-slate-900 block mb-1 uppercase tracking-wider text-[11px]">
                      Clarification Questions for Patient:
                    </span>
                    <ul className="list-disc pl-4 space-y-1 text-slate-600">
                      {brief.clarificationQuestions.map((q, idx) => (
                        <li key={idx}>{q}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <span className="font-bold text-slate-900 block mb-1 uppercase tracking-wider text-[11px]">
                      Recorded Unknowns:
                    </span>
                    <ul className="list-disc pl-4 space-y-1 text-slate-500">
                      {brief.unknowns.map((u, idx) => (
                        <li key={idx}>{u}</li>
                      ))}
                    </ul>
                  </div>
                </>
              ) : (
                <p className="text-slate-400 italic">No brief available for this case.</p>
              )
            ) : (
              <div className="space-y-3">
                {docs.length === 0 ? (
                  <p className="text-slate-400 italic">No files attached by patient.</p>
                ) : (
                  docs.map((d) => (
                    <div key={d.documentId} className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-800">{d.fileName}</span>
                        <span className="text-[10px] text-emerald-700 font-bold bg-emerald-100 px-2 py-0.5 rounded">Signed URL 15m</span>
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
            <span className="text-xs font-mono text-slate-500">Dr. Rajesh Patil</span>
          </div>

          <form onSubmit={handleComplete} className="space-y-5">
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
