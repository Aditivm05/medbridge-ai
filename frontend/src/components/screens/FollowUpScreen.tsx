import React, { useState } from 'react';
import { Calendar, CheckCircle2, ArrowLeft, HeartHandshake } from 'lucide-react';
import { CaseData, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { SimulationBadge } from '../common/SimulationBadge';

interface FollowUpScreenProps {
  currentCase: CaseData;
  language: LanguageCode;
  onBack: () => void;
  onFinalizeCase: (followUp: { required: boolean; recommendedDate: string; instructions: string }) => void;
}

export const FollowUpScreen: React.FC<FollowUpScreenProps> = ({
  currentCase,
  language,
  onBack,
  onFinalizeCase,
}) => {
  const t = getTranslation(language);
  const [required, setRequired] = useState(true);
  const [recommendedDate, setRecommendedDate] = useState('2026-10-15');
  const [instructions, setInstructions] = useState(
    'If right lower quadrant abdominal tenderness intensifies, high fever spikes above 101.5°F, or repeated vomiting occurs, immediately report to the nearest hospital emergency room. Otherwise, schedule clinical ultrasound review in 5 days.'
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!instructions.trim()) return;
    onFinalizeCase({
      required,
      recommendedDate,
      instructions,
    });
  };

  const isCompleted = currentCase.status === 'COMPLETED';

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-8 shadow-xs">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-100 mb-6">
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
              <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
                {t.followUpTitle}
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
                {t.followUpSubtitle}
              </p>
            </div>
          </div>
          <SimulationBadge />
        </div>

        {/* Completed Case Banner if viewing finalized */}
        {isCompleted && (
          <div className="mb-6 p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-start gap-3 text-emerald-950">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <strong className="block font-bold text-emerald-900 text-sm">
                {t.caseCompletedBadge}
              </strong>
              <p className="text-xs text-emerald-800 mt-0.5">
                Care coordination concluded on {new Date(currentCase.completedAt || '').toLocaleString()}. Patient has received consultation notes and scheduled follow-up guidance.
              </p>
            </div>
          </div>
        )}

        {/* Consultation Notes Summary */}
        {currentCase.consultation && (
          <div className="mb-6 rounded-xl border border-slate-200 p-4 bg-slate-50 space-y-3 text-xs text-slate-700">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <span className="font-bold text-slate-900 flex items-center gap-1.5">
                <HeartHandshake className="w-4 h-4 text-brand-600" />
                Clinician Consultation Record
              </span>
              <span className="font-semibold text-teal-800">{currentCase.consultation.clinicianName}</span>
            </div>

            <div>
              <span className="font-bold text-slate-800 block mb-0.5">Assessment:</span>
              <p className="text-slate-700 leading-relaxed">{currentCase.consultation.clinicianNotes}</p>
            </div>

            <div>
              <span className="font-bold text-slate-800 block mb-0.5">Supportive Care Advice:</span>
              <p className="text-slate-700 leading-relaxed">{currentCase.consultation.provisionalCareAdvice}</p>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Required Checkbox */}
          <div className="flex items-center gap-3 p-4 rounded-xl bg-slate-50 border border-slate-200">
            <input
              id="followUpRequired"
              type="checkbox"
              checked={required}
              onChange={(e) => setRequired(e.target.checked)}
              disabled={isCompleted}
              className="w-4 h-4 text-brand-600 rounded border-slate-300 focus:ring-brand-500 cursor-pointer"
            />
            <label htmlFor="followUpRequired" className="text-xs sm:text-sm font-bold text-slate-800 cursor-pointer">
              {t.followUpRequiredLabel}
            </label>
          </div>

          {/* Recommended Date */}
          {required && (
            <div>
              <label htmlFor="recommendedDate" className="block text-sm font-bold text-slate-800 mb-1.5">
                {t.followUpDateLabel} <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <Calendar className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                <input
                  id="recommendedDate"
                  type="date"
                  value={recommendedDate}
                  onChange={(e) => setRecommendedDate(e.target.value)}
                  disabled={isCompleted}
                  className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 text-xs sm:text-sm text-slate-800 outline-hidden disabled:bg-slate-100"
                  required
                />
              </div>
            </div>
          )}

          {/* Instructions */}
          <div>
            <label htmlFor="instructions" className="block text-sm font-bold text-slate-800 mb-1.5">
              {t.followUpInstructionsLabel} <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="instructions"
              rows={4}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              disabled={isCompleted}
              placeholder={t.followUpInstructionsPlaceholder}
              className="w-full p-3.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 text-xs sm:text-sm text-slate-800 outline-hidden disabled:bg-slate-100"
              required
            />
          </div>

          {/* Action Row */}
          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={onBack}
              className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
            >
              Back
            </button>

            {!isCompleted ? (
              <button
                type="submit"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 active:scale-95 text-white font-bold text-sm shadow-md shadow-emerald-600/20 transition-all cursor-pointer"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>{t.finalizeCaseBtn}</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={onBack}
                className="px-5 py-2.5 rounded-xl bg-slate-900 text-white font-bold text-xs cursor-pointer"
              >
                Return to Dashboard
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
};
