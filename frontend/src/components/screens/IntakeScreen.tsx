import React, { useState } from 'react';
import { AlertCircle, CheckCircle2, Clock, ArrowRight, ArrowLeft } from 'lucide-react';
import { LanguageCode, RequestedUrgency } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { EmergencyBanner } from '../common/EmergencyBanner';
import { SimulationBadge } from '../common/SimulationBadge';

interface IntakeScreenProps {
  language: LanguageCode;
  onBack: () => void;
  onSubmitIntake: (data: {
    chiefComplaint: string;
    duration: string;
    requestedUrgency: RequestedUrgency;
    patientLanguage: LanguageCode;
    symptoms: string[];
    knownConditions?: string;
    medications?: string;
    allergies?: string;
  }) => void;
}

const COMMON_SYMPTOMS = [
  'High Fever (102°F+)',
  'Sharp Abdominal Pain',
  'Chest Tightness',
  'Severe Headache',
  'Difficulty Breathing',
  'Nausea / Vomiting',
  'Persistent Cough',
  'Dizziness / Vertigo',
];

export const IntakeScreen: React.FC<IntakeScreenProps> = ({
  language,
  onBack,
  onSubmitIntake,
}) => {
  const t = getTranslation(language);
  const [urgency, setUrgency] = useState<RequestedUrgency>('urgent');
  const [chiefComplaint, setChiefComplaint] = useState('');
  const [duration, setDuration] = useState('');
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [knownConditions, setKnownConditions] = useState('');
  const [medications, setMedications] = useState('');
  const [allergies, setAllergies] = useState('');

  const toggleSymptom = (symptom: string) => {
    if (selectedSymptoms.includes(symptom)) {
      setSelectedSymptoms(selectedSymptoms.filter((s) => s !== symptom));
    } else {
      setSelectedSymptoms([...selectedSymptoms, symptom]);
      // If chief complaint is empty, provide default text
      if (!chiefComplaint) {
        setChiefComplaint(symptom);
      }
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chiefComplaint.trim() || !duration.trim()) return;

    onSubmitIntake({
      chiefComplaint,
      duration,
      requestedUrgency: urgency,
      patientLanguage: language,
      symptoms: selectedSymptoms,
      knownConditions,
      medications,
      allergies,
    });
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      {/* Static Emergency Guidance triggers immediately on Urgent/Emergency */}
      {(urgency === 'urgent' || urgency === 'emergency') && (
        <EmergencyBanner language={language} />
      )}

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
                {t.intakeTitle}
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
                {t.intakeSubtitle}
              </p>
            </div>
          </div>
          <SimulationBadge />
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Urgency Level Selector */}
          <div>
            <label className="block text-sm font-bold text-slate-800 mb-2">
              {t.selectUrgency} <span className="text-rose-500">*</span>
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Routine */}
              <button
                type="button"
                onClick={() => setUrgency('routine')}
                className={`p-3.5 rounded-xl border text-left transition-all flex flex-col justify-between cursor-pointer ${
                  urgency === 'routine'
                    ? 'border-brand-600 bg-brand-50/50 ring-2 ring-brand-500/20'
                    : 'border-slate-200 hover:border-slate-300 bg-white'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-sm text-slate-900">
                    {t.urgencyRoutine}
                  </span>
                  {urgency === 'routine' && <CheckCircle2 className="w-4 h-4 text-brand-600" />}
                </div>
                <span className="text-xs text-slate-500 mt-2">{t.urgencyDescRoutine}</span>
              </button>

              {/* Urgent */}
              <button
                type="button"
                onClick={() => setUrgency('urgent')}
                className={`p-3.5 rounded-xl border text-left transition-all flex flex-col justify-between cursor-pointer ${
                  urgency === 'urgent'
                    ? 'border-urgent-500 bg-urgent-50/60 ring-2 ring-urgent-500/20'
                    : 'border-slate-200 hover:border-slate-300 bg-white'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-sm text-amber-900">
                    {t.urgencyUrgent}
                  </span>
                  {urgency === 'urgent' && <CheckCircle2 className="w-4 h-4 text-urgent-600" />}
                </div>
                <span className="text-xs text-amber-700 mt-2">{t.urgencyDescUrgent}</span>
              </button>

              {/* Emergency */}
              <button
                type="button"
                onClick={() => setUrgency('emergency')}
                className={`p-3.5 rounded-xl border text-left transition-all flex flex-col justify-between cursor-pointer ${
                  urgency === 'emergency'
                    ? 'border-emergency-600 bg-emergency-50 ring-2 ring-emergency-600/30'
                    : 'border-slate-200 hover:border-slate-300 bg-white'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-sm text-emergency-700">
                    {t.urgencyEmergency}
                  </span>
                  {urgency === 'emergency' && <AlertCircle className="w-4 h-4 text-emergency-600" />}
                </div>
                <span className="text-xs text-emergency-600 mt-2 font-medium">{t.urgencyDescEmergency}</span>
              </button>
            </div>
          </div>

          {/* Quick Symptoms Toggles */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
              {t.commonSymptomsTitle}
            </label>
            <div className="flex flex-wrap gap-2">
              {COMMON_SYMPTOMS.map((sym) => {
                const isSelected = selectedSymptoms.includes(sym);
                return (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => toggleSymptom(sym)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                      isSelected
                        ? 'bg-brand-600 border-brand-700 text-white shadow-xs'
                        : 'bg-slate-100 border-slate-200 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    {sym}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Chief Complaint Textarea */}
          <div>
            <label htmlFor="chiefComplaint" className="block text-sm font-bold text-slate-800 mb-1.5">
              {t.chiefComplaintLabel} <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="chiefComplaint"
              rows={4}
              value={chiefComplaint}
              onChange={(e) => setChiefComplaint(e.target.value)}
              placeholder={t.chiefComplaintPlaceholder}
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 text-sm outline-hidden text-slate-800"
              required
            />
          </div>

          {/* Duration Input */}
          <div>
            <label htmlFor="duration" className="block text-sm font-bold text-slate-800 mb-1.5">
              {t.durationLabel} <span className="text-rose-500">*</span>
            </label>
            <div className="relative">
              <Clock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
              <input
                id="duration"
                type="text"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                placeholder={t.durationPlaceholder}
                className="w-full pl-10 pr-3.5 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 text-sm outline-hidden text-slate-800"
                required
              />
            </div>
          </div>

          {/* Optional Clinical Context Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 border-t border-slate-100">
            <div>
              <label htmlFor="knownConditions" className="block text-xs font-semibold text-slate-600 mb-1">
                {t.knownConditionsLabel}
              </label>
              <input
                id="knownConditions"
                type="text"
                value={knownConditions}
                onChange={(e) => setKnownConditions(e.target.value)}
                placeholder={t.knownConditionsPlaceholder}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs focus:ring-2 focus:ring-brand-500 outline-hidden"
              />
            </div>

            <div>
              <label htmlFor="medications" className="block text-xs font-semibold text-slate-600 mb-1">
                {t.currentMedicationsLabel}
              </label>
              <input
                id="medications"
                type="text"
                value={medications}
                onChange={(e) => setMedications(e.target.value)}
                placeholder={t.currentMedicationsPlaceholder}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs focus:ring-2 focus:ring-brand-500 outline-hidden"
              />
            </div>

            <div>
              <label htmlFor="allergies" className="block text-xs font-semibold text-slate-600 mb-1">
                {t.allergiesLabel}
              </label>
              <input
                id="allergies"
                type="text"
                value={allergies}
                onChange={(e) => setAllergies(e.target.value)}
                placeholder={t.allergiesPlaceholder}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs focus:ring-2 focus:ring-brand-500 outline-hidden"
              />
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={onBack}
              className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={!chiefComplaint.trim() || !duration.trim()}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-700 active:scale-95 text-white font-bold text-sm shadow-md shadow-brand-500/20 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span>{t.saveAndUploadBtn}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
