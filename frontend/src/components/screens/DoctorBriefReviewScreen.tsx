import React, { useState } from 'react';
import { 
  ShieldAlert, 
  CheckCircle2, 
  Edit3, 
  FileText, 
  HelpCircle, 
  AlertTriangle, 
  ArrowLeft, 
  Sparkles, 
  Layers 
} from 'lucide-react';
import { CaseData, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { SimulationBadge } from '../common/SimulationBadge';

interface DoctorBriefReviewScreenProps {
  currentCase: CaseData;
  language: LanguageCode;
  onBack: () => void;
  onApproveAndEnqueue: () => void;
  onSaveCorrections: (corrections: string) => void;
}

export const DoctorBriefReviewScreen: React.FC<DoctorBriefReviewScreenProps> = ({
  currentCase,
  language,
  onBack,
  onApproveAndEnqueue,
  onSaveCorrections,
}) => {
  const t = getTranslation(language);
  const brief = currentCase.doctorBrief;

  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [correctionText, setCorrectionText] = useState('');

  if (!brief) {
    return (
      <div className="bg-white rounded-2xl p-8 text-center border border-slate-200">
        <div className="w-8 h-8 border-3 border-brand-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm font-bold text-slate-700">Synthesizing Doctor Brief with Gemini...</p>
      </div>
    );
  }

  const handleSaveEdit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!correctionText.trim()) return;
    onSaveCorrections(correctionText);
    setIsEditModalOpen(false);
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Top Banner Notice */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-7 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100 mb-5">
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
                  {t.briefReviewTitle}
                </h2>
                <span className="text-[11px] font-mono font-bold bg-teal-100 text-teal-800 px-2 py-0.5 rounded">
                  v{brief.schemaVersion}
                </span>
              </div>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
                {t.briefReviewSubtitle}
              </p>
            </div>
          </div>

          <SimulationBadge />
        </div>

        {/* NON-NEGOTIABLE SAFETY DISCLAIMER */}
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 mb-6 flex items-start gap-3 text-amber-950">
          <ShieldAlert className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed">
            <strong className="block font-bold uppercase tracking-wider text-amber-900 mb-0.5">
              {t.briefDisclaimerTitle}
            </strong>
            {brief.disclaimer}
          </div>
        </div>

        {/* Section 1: Patient-Reported Subjective Findings */}
        <div className="mb-6 rounded-xl border border-slate-200 overflow-hidden">
          <div className="bg-slate-50 px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
            <h3 className="text-xs font-black uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-brand-600" />
              {t.briefPatientReportedTitle}
            </h3>
            <span className="text-[10px] font-semibold text-slate-500">Source: Patient Input</span>
          </div>

          <div className="p-4 space-y-3 text-xs text-slate-700 bg-white">
            <div>
              <span className="font-bold text-slate-900 block">Primary Concern:</span>
              <p className="mt-0.5 text-slate-800">{brief.patientReported.chiefComplaint}</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-100">
              <div>
                <span className="font-bold text-slate-900 block">Reported Symptoms:</span>
                <ul className="list-disc pl-4 mt-0.5 space-y-0.5 text-slate-700">
                  {brief.patientReported.symptoms.map((s, idx) => (
                    <li key={idx}>{s}</li>
                  ))}
                </ul>
              </div>

              <div>
                <span className="font-bold text-slate-900 block">Timeline / Duration:</span>
                <p className="mt-0.5">{brief.patientReported.timelineDuration}</p>

                <span className="font-bold text-slate-900 block mt-2">Allergies:</span>
                <p className="mt-0.5 text-rose-700 font-semibold">{brief.patientReported.allergies.join(', ') || 'None reported'}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Section 2: Document-Extracted Objective Clinical Facts */}
        <div className="mb-6 rounded-xl border border-slate-200 overflow-hidden">
          <div className="bg-teal-50/70 px-4 py-2.5 border-b border-teal-200 flex items-center justify-between">
            <h3 className="text-xs font-black uppercase tracking-wider text-teal-950 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-teal-700" />
              {t.briefExtractedFactsTitle}
            </h3>
            <span className="text-[10px] font-bold text-teal-800 bg-teal-100 px-2 py-0.5 rounded">
              {t.unitsPreservedBadge}
            </span>
          </div>

          <div className="p-4 bg-white">
            {brief.extractedFacts.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No objective lab findings extracted.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                      <th className="py-2 pr-3">Clinical Parameter</th>
                      <th className="py-2 px-3">Extracted Value & Unit</th>
                      <th className="py-2 pl-3">Source Document</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {brief.extractedFacts.map((fact, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 pr-3 font-bold text-slate-900">{fact.fact}</td>
                        <td className="py-2.5 px-3 font-mono font-bold text-brand-700">
                          {fact.value} {fact.unit}
                        </td>
                        <td className="py-2.5 pl-3 text-slate-500 font-mono text-[11px]">
                          {fact.sourceDocumentId} (p. {fact.pageNumber || 1})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Section 3 & 4 Grid: Explicit Unknowns & Missing Info */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
          {/* Unknowns */}
          <div className="rounded-xl border border-slate-200 overflow-hidden">
            <div className="bg-slate-50 px-4 py-2 border-b border-slate-200">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                {t.briefUnknownsTitle}
              </h4>
            </div>
            <div className="p-3.5 bg-white space-y-1.5">
              {brief.unknowns.map((u, idx) => (
                <div key={idx} className="flex items-start gap-1.5 text-xs text-slate-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0 mt-1.5" />
                  <span>{u}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Missing Context */}
          <div className="rounded-xl border border-slate-200 overflow-hidden">
            <div className="bg-slate-50 px-4 py-2 border-b border-slate-200">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                {t.briefMissingInfoTitle}
              </h4>
            </div>
            <div className="p-3.5 bg-white space-y-1.5">
              {brief.missingInformation.map((m, idx) => (
                <div key={idx} className="flex items-start gap-1.5 text-xs text-amber-800">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                  <span>{m}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Section 5: Clarification Questions for Clinician */}
        <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50/40 p-4">
          <h4 className="text-xs font-bold uppercase tracking-wider text-blue-900 mb-2 flex items-center gap-1.5">
            <HelpCircle className="w-3.5 h-3.5 text-blue-600" />
            {t.briefQuestionsTitle}
          </h4>
          <ul className="space-y-1.5 pl-2">
            {brief.clarificationQuestions.map((q, idx) => (
              <li key={idx} className="text-xs text-blue-950 flex items-start gap-2">
                <span className="font-bold text-blue-600 font-mono">Q{idx + 1}.</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Section 6: Source References */}
        <div className="mb-6 rounded-xl border border-slate-200 p-4 bg-slate-50/60">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-slate-500" />
            {t.briefSourcesTitle}
          </h4>
          <div className="space-y-1.5">
            {brief.sources.map((src, idx) => (
              <div key={idx} className="text-xs text-slate-600 flex items-center gap-2">
                <span className="font-mono text-[10px] bg-slate-200 px-1.5 py-0.5 rounded uppercase">
                  {src.sourceType}
                </span>
                <span className="font-semibold text-slate-800">{src.sourceId}:</span>
                <span className="text-slate-600 truncate">{src.referenceText}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Action Row: Human-in-the-Loop Approval Gate */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-slate-200">
          <button
            type="button"
            onClick={() => setIsEditModalOpen(true)}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-slate-300 hover:bg-slate-100 text-xs font-bold text-slate-700 transition-colors cursor-pointer"
          >
            <Edit3 className="w-3.5 h-3.5" />
            <span>{t.suggestEditBtn}</span>
          </button>

          <button
            type="button"
            onClick={onApproveAndEnqueue}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 active:scale-95 text-white font-bold text-sm shadow-md shadow-emerald-600/20 transition-all cursor-pointer"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>{t.approveBriefBtn}</span>
          </button>
        </div>
      </div>

      {/* Suggest Correction Modal */}
      {isEditModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200">
            <h3 className="text-base font-bold text-slate-900 mb-2">
              {t.editModalTitle}
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              Enter any details that need correction in your patient-reported symptoms or timeline:
            </p>
            <form onSubmit={handleSaveEdit}>
              <textarea
                rows={4}
                value={correctionText}
                onChange={(e) => setCorrectionText(e.target.value)}
                placeholder="e.g., Note: Pain started 48 hours ago instead of 36 hours; fever has come down slightly to 101°F after taking fluids."
                className="w-full p-3 rounded-xl border border-slate-300 text-xs focus:ring-2 focus:ring-brand-500 outline-hidden mb-4"
                required
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-brand-600 text-white text-xs font-bold shadow hover:bg-brand-700 cursor-pointer"
                >
                  {t.saveCorrectionsBtn}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
