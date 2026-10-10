import React, { useState, useEffect } from 'react';
import { 
  Stethoscope,
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  FileText, 
  ArrowRight, 
  Sparkles, 
  UserCheck,
  RefreshCw,
  XCircle,
  ShieldAlert,
} from 'lucide-react';
import { CaseData, ClinicianData, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { mockClinicians } from '../../services/mockData';
import { api } from '../../services/api';
import { authService } from '../../services/authService';
import { StatusBadge } from '../common/StatusBadge';
import { SimulationBadge } from '../common/SimulationBadge';

interface ClinicianDashboardProps {
  cases: CaseData[];
  language: LanguageCode;
  onClaimCase: (
    caseId: string,
    clinicianId: string,
    simulateConflict?: boolean
  ) => Promise<{ success: boolean; error?: string }> | void;
  onDeclineCase?: (
    caseId: string,
    reason?: string
  ) => Promise<{ success: boolean; error?: string }> | void;
  onOpenConsultation: (caseItem: CaseData) => void;
  onRefreshPool?: () => Promise<void> | void;
}

export const ClinicianDashboard: React.FC<ClinicianDashboardProps> = ({
  cases,
  language,
  onClaimCase,
  onDeclineCase,
  onOpenConsultation,
  onRefreshPool,
}) => {
  const t = getTranslation(language);
  const currentSession = authService.getCurrentSession();
  const initialClinicianId = currentSession.role === 'clinician' ? currentSession.uid : 'demo_doc_patil';

  const [clinicians, setClinicians] = useState<ClinicianData[]>(mockClinicians);
  const [selectedClinicianId, setSelectedClinicianId] = useState<string>(initialClinicianId);
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const [isClaiming, setIsClaiming] = useState<string | null>(null);
  const [isDeclining, setIsDeclining] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isUpdatingAvailability, setIsUpdatingAvailability] = useState(false);

  // Sync clinicians list from backend API on mount
  useEffect(() => {
    api.listClinicians()
      .then((docs) => {
        if (Array.isArray(docs) && docs.length > 0) {
          setClinicians(docs);
        }
      })
      .catch(() => {
        // Fallback to seeded mockClinicians
      });

    if (onRefreshPool) {
      onRefreshPool();
    }
  }, []);

  const activeClinician = clinicians.find((c) => c.clinicianId === selectedClinicianId) || clinicians[0] || mockClinicians[0];

  // Cases waiting in matching pool
  const matchingPoolCases = cases.filter((c) => c.status === 'MATCHING' && !c.assignedClinicianId);

  // Cases claimed by current clinician
  const myClaimedCases = cases.filter(
    (c) => c.assignedClinicianId === activeClinician.clinicianId || c.status === 'ACCEPTED' || c.status === 'IN_CONSULTATION'
  );

  const handleSelectClinician = (newId: string) => {
    setSelectedClinicianId(newId);
    setConflictMessage(null);
    authService.switchUser(newId);
  };

  const handleToggleAvailability = async (newAvailability: 'available' | 'busy' | 'offline') => {
    setIsUpdatingAvailability(true);
    setConflictMessage(null);
    try {
      await api.updateClinicianAvailability(activeClinician.clinicianId, newAvailability);
      setClinicians((prev) =>
        prev.map((c) =>
          c.clinicianId === activeClinician.clinicianId
            ? { ...c, availability: newAvailability }
            : c
        )
      );
    } catch (err: any) {
      // Local optimistic fallback
      setClinicians((prev) =>
        prev.map((c) =>
          c.clinicianId === activeClinician.clinicianId
            ? { ...c, availability: newAvailability }
            : c
        )
      );
    } finally {
      setIsUpdatingAvailability(false);
    }
  };

  const handleClaim = async (caseId: string, simulateConflict: boolean = false) => {
    setConflictMessage(null);
    setIsClaiming(caseId);

    try {
      const res = await onClaimCase(caseId, activeClinician.clinicianId, simulateConflict);
      if (res && !res.success && res.error) {
        setConflictMessage(res.error);
      }
    } catch (err: any) {
      setConflictMessage(err.message || 'Error claiming case');
    } finally {
      setIsClaiming(null);
    }
  };

  const handleDecline = async (caseId: string) => {
    if (!onDeclineCase) return;
    setConflictMessage(null);
    setIsDeclining(caseId);

    try {
      const res = await onDeclineCase(caseId, 'Clinician unavailable / outside scope');
      if (res && !res.success && res.error) {
        setConflictMessage(res.error);
      }
    } catch (err: any) {
      setConflictMessage(err.message || 'Error declining case');
    } finally {
      setIsDeclining(null);
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setConflictMessage(null);
    try {
      if (onRefreshPool) {
        await onRefreshPool();
      }
      const docs = await api.listClinicians();
      if (Array.isArray(docs) && docs.length > 0) {
        setClinicians(docs);
      }
    } catch {} finally {
      setIsRefreshing(false);
    }
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
              onChange={(e) => handleSelectClinician(e.target.value)}
              className="text-xs font-bold bg-transparent border-0 focus:ring-0 text-slate-800 cursor-pointer outline-hidden"
              aria-label="Clinician Profile"
            >
              {clinicians.map((doc) => (
                <option key={doc.clinicianId} value={doc.clinicianId}>
                  {doc.fullName} ({doc.specialty})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Active Clinician Banner */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-600 bg-teal-50/60 p-3 rounded-xl border border-teal-200">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-teal-950">{activeClinician.fullName}</span>
            <span className="font-mono text-[11px] text-teal-700 bg-teal-100 px-2 py-0.5 rounded">
              License: {activeClinician.licenseNumber}
            </span>
            {activeClinician.verificationStatus === 'verified' ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded">
                Verified
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded">
                Pending Verification
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <span className="text-[11px] font-semibold text-slate-500 hidden md:inline">
              Languages: {activeClinician.languages.map((l) => l.toUpperCase()).join(', ')}
            </span>

            {/* Availability Selector */}
            <div className="flex items-center gap-1.5 bg-white px-2 py-1 rounded-lg border border-teal-200 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400">Status:</span>
              <select
                value={activeClinician.availability}
                disabled={isUpdatingAvailability}
                onChange={(e) => handleToggleAvailability(e.target.value as any)}
                aria-label="Clinician Availability"
                className={`text-[11px] font-bold bg-transparent border-0 focus:ring-0 cursor-pointer outline-hidden ${
                  activeClinician.availability === 'available'
                    ? 'text-emerald-700 font-extrabold'
                    : activeClinician.availability === 'busy'
                    ? 'text-amber-700 font-extrabold'
                    : 'text-slate-500 font-bold'
                }`}
              >
                <option value="available">Available</option>
                <option value="busy">Busy (In Case)</option>
                <option value="offline">Offline</option>
              </select>
            </div>
          </div>
        </div>

        {/* Unverified Clinician Alert Banner */}
        {activeClinician.verificationStatus !== 'verified' && (
          <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-center gap-2 text-amber-900 text-xs">
            <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              <strong>Unverified Clinician Profile:</strong> Backend policy strictly enforces HTTP 403 Forbidden on case acceptance for pending credentials.
            </span>
          </div>
        )}
      </div>

      {/* Race Collision Banner if triggered */}
      {conflictMessage && (
        <div className="p-4 bg-rose-50 border-2 border-rose-300 rounded-xl flex items-start gap-3 text-rose-900 animate-shake">
          <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="text-xs">
            <strong className="block font-bold mb-0.5 uppercase tracking-wide">
              Case Coordination Message
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
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="inline-flex items-center gap-1 text-[11px] font-bold text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-50 border border-slate-200 px-2.5 py-1 rounded-lg cursor-pointer transition-colors shadow-2xs disabled:opacity-50"
              title="Refresh matching queue from backend"
            >
              <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
              <span>Refresh Queue</span>
            </button>
            <SimulationBadge size="sm" />
          </div>
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

                {/* Claim and Decline Buttons */}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => handleClaim(caseItem.caseId, true)}
                    disabled={isClaiming === caseItem.caseId || isDeclining === caseItem.caseId}
                    className="px-3 py-1.5 rounded-lg border border-rose-300 text-rose-700 hover:bg-rose-50 text-xs font-bold transition-colors cursor-pointer disabled:opacity-50"
                    title="Simulate two clinicians clicking accept at the same millisecond"
                  >
                    {t.simulateConflictBtn}
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleDecline(caseItem.caseId)}
                      disabled={isClaiming === caseItem.caseId || isDeclining === caseItem.caseId}
                      className="inline-flex items-center gap-1 px-3.5 py-2 rounded-xl border border-slate-300 hover:bg-slate-100 text-slate-700 font-bold text-xs transition-colors cursor-pointer disabled:opacity-50"
                    >
                      <XCircle className="w-3.5 h-3.5 text-slate-400" />
                      <span>{isDeclining === caseItem.caseId ? t.decliningCase : t.declineCaseBtn}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleClaim(caseItem.caseId, false)}
                      disabled={isClaiming === caseItem.caseId || isDeclining === caseItem.caseId}
                      className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs shadow-md shadow-purple-600/20 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      <span>{isClaiming === caseItem.caseId ? t.claimingCase : t.claimCaseBtn}</span>
                    </button>
                  </div>
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
