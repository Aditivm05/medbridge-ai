import React, { useState } from 'react';
import { 
  Stethoscope,
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  FileText, 
  ArrowRight, 
  Sparkles, 
  UserCheck 
} from 'lucide-react';
import { CaseData, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { mockClinicians } from '../../services/mockData';
import { StatusBadge } from '../common/StatusBadge';
import { SimulationBadge } from '../common/SimulationBadge';

interface ClinicianDashboardProps {
  cases: CaseData[];
  language: LanguageCode;
  onClaimCase: (caseId: string, clinicianId: string, simulateConflict?: boolean) => void;
  onOpenConsultation: (caseItem: CaseData) => void;
}

export const ClinicianDashboard: React.FC<ClinicianDashboardProps> = ({
  cases,
  language,
  onClaimCase,
  onOpenConsultation,
}) => {
  const t = getTranslation(language);
  const [selectedClinicianId, setSelectedClinicianId] = useState('demo_doc_patil');
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);

  const activeClinician = mockClinicians.find((c) => c.clinicianId === selectedClinicianId) || mockClinicians[0];

  // Cases waiting in matching pool
  const matchingPoolCases = cases.filter((c) => c.status === 'MATCHING' && !c.assignedClinicianId);

  // Cases claimed by current clinician
  const myClaimedCases = cases.filter(
    (c) => c.assignedClinicianId === activeClinician.clinicianId || c.status === 'ACCEPTED' || c.status === 'IN_CONSULTATION'
  );

  const handleClaim = (caseId: string, simulateConflict: boolean = false) => {
    setConflictMessage(null);
    if (simulateConflict) {
      setConflictMessage(t.conflictDetectedMsg);
    }
    onClaimCase(caseId, activeClinician.clinicianId, simulateConflict);
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Clinician Profile Selector Header */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100 mb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
                {t.clinicianDashboardTitle}
              </h2>
              <SimulationBadge />
            </div>
            <p className="text-xs sm:text-sm text-slate-500 font-medium">
              {t.clinicianDashboardSubtitle}
            </p>
          </div>

          {/* Clinician Persona Switcher */}
          <div className="flex items-center gap-2 bg-slate-50 p-1.5 rounded-xl border border-slate-200">
            <UserCheck className="w-4 h-4 text-brand-600 shrink-0 ml-1" />
            <select
              value={selectedClinicianId}
              onChange={(e) => setSelectedClinicianId(e.target.value)}
              className="text-xs font-bold bg-transparent border-0 focus:ring-0 text-slate-800 cursor-pointer outline-hidden"
              aria-label="Clinician Profile"
            >
              {mockClinicians.map((doc) => (
                <option key={doc.clinicianId} value={doc.clinicianId}>
                  {doc.fullName} ({doc.specialty})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Active Clinician Banner */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600 bg-teal-50/60 p-3 rounded-xl border border-teal-200">
          <div className="flex items-center gap-2">
            <span className="font-bold text-teal-950">{activeClinician.fullName}</span>
            <span className="font-mono text-[11px] text-teal-700 bg-teal-100 px-2 py-0.5 rounded">
              License: {activeClinician.licenseNumber}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold text-slate-500">
              Languages: {activeClinician.languages.map((l) => l.toUpperCase()).join(', ')}
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Available
            </span>
          </div>
        </div>
      </div>

      {/* Race Collision Banner if triggered */}
      {conflictMessage && (
        <div className="p-4 bg-rose-50 border-2 border-rose-300 rounded-xl flex items-start gap-3 text-rose-900 animate-shake">
          <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="text-xs">
            <strong className="block font-bold mb-0.5 uppercase tracking-wide">
              Concurrency Collision Handled (HTTP 409 Conflict)
            </strong>
            {conflictMessage}
          </div>
        </div>
      )}

      {/* Matching Pool Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand-600" />
            {t.availableQueueTitle} ({matchingPoolCases.length})
          </h3>
          <SimulationBadge size="sm" />
        </div>

        {matchingPoolCases.length === 0 ? (
          <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-8 text-center text-slate-400 text-xs italic">
            No unassigned cases in the matching pool. Cases will appear here as soon as patients review and approve their briefs.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {matchingPoolCases.map((caseItem) => (
              <div
                key={caseItem.caseId}
                className="bg-white rounded-2xl p-5 border-2 border-purple-200 hover:border-purple-400 shadow-xs transition-all relative overflow-hidden"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1 text-[11px] font-black uppercase tracking-wider px-2.5 py-0.5 rounded-full ${
                        caseItem.requestedUrgency === 'emergency'
                          ? 'bg-rose-100 text-rose-800'
                          : 'bg-amber-100 text-amber-900'
                      }`}
                    >
                      {caseItem.requestedUrgency}
                    </span>
                    <span className="text-xs font-mono font-semibold text-slate-400">
                      #{caseItem.caseId.substring(0, 14)}
                    </span>
                    <span className="text-[11px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded uppercase">
                      Lang: {caseItem.patientLanguage}
                    </span>
                  </div>

                  <StatusBadge status={caseItem.status} language={language} />
                </div>

                <h4 className="text-base font-bold text-slate-900 mb-2">
                  {caseItem.chiefComplaint}
                </h4>

                <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 mb-4">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                    Timeline: {caseItem.duration}
                  </span>
                  <span className="flex items-center gap-1">
                    <FileText className="w-3.5 h-3.5 text-slate-400" />
                    Lab Reports: {caseItem.documentCount}
                  </span>
                  <span className="text-teal-700 font-semibold">
                    Doctor Brief: Ready & Approved by Patient
                  </span>
                </div>

                {/* Claim Buttons */}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => handleClaim(caseItem.caseId, true)}
                    className="px-3 py-1.5 rounded-lg border border-rose-300 text-rose-700 hover:bg-rose-50 text-xs font-bold transition-colors cursor-pointer"
                    title="Simulate two clinicians clicking accept at the same millisecond"
                  >
                    {t.simulateConflictBtn}
                  </button>

                  <button
                    type="button"
                    onClick={() => handleClaim(caseItem.caseId, false)}
                    className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs shadow-md shadow-purple-600/20 active:scale-95 transition-all cursor-pointer"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    <span>{t.claimCaseBtn}</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Claimed Cases In Consultation */}
      <div className="space-y-4 pt-4 border-t border-slate-200">
        <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
          <Stethoscope className="w-4 h-4 text-brand-600" />
          Active Consultations ({myClaimedCases.length})
        </h3>

        {myClaimedCases.length === 0 ? (
          <p className="text-xs text-slate-400 italic">No claimed cases in consultation for this clinician.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {myClaimedCases.map((caseItem) => (
              <div
                key={caseItem.caseId}
                onClick={() => onOpenConsultation(caseItem)}
                className="p-4 bg-white rounded-xl border border-slate-200 hover:border-brand-500 shadow-xs flex items-center justify-between cursor-pointer transition-colors"
              >
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono font-bold text-slate-500">#{caseItem.caseId.substring(0, 14)}</span>
                    <StatusBadge status={caseItem.status} language={language} />
                  </div>
                  <h5 className="text-sm font-bold text-slate-900 line-clamp-1">{caseItem.chiefComplaint}</h5>
                </div>

                <div className="flex items-center gap-1 text-xs font-bold text-brand-600 shrink-0">
                  <span>Open Workspace</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
