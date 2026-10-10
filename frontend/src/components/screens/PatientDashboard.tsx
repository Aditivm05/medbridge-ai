import React, { useState } from 'react';
import { PlusCircle, FileText, ArrowRight, Clock, AlertTriangle, ShieldCheck, Inbox } from 'lucide-react';
import { CaseData, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { StatusBadge } from '../common/StatusBadge';
import { SimulationBadge } from '../common/SimulationBadge';

interface PatientDashboardProps {
  cases: CaseData[];
  language: LanguageCode;
  onStartNewRequest: () => void;
  onOpenCase: (caseItem: CaseData) => void;
}

export const PatientDashboard: React.FC<PatientDashboardProps> = ({
  cases,
  language,
  onStartNewRequest,
  onOpenCase,
}) => {
  const t = getTranslation(language);
  const [filter, setFilter] = useState<'all' | 'active' | 'completed'>('all');

  const filteredCases = cases.filter((c) => {
    if (filter === 'active') return c.status !== 'COMPLETED' && c.status !== 'CANCELLED';
    if (filter === 'completed') return c.status === 'COMPLETED';
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Dashboard Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-5 sm:p-6 rounded-2xl border border-slate-200 shadow-xs">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
              {t.patientDashboardTitle}
            </h2>
            <SimulationBadge />
          </div>
          <p className="text-xs sm:text-sm text-slate-500 font-medium">
            {t.patientDashboardSubtitle}
          </p>
        </div>

        <button
          type="button"
          onClick={onStartNewRequest}
          className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-brand-600 hover:bg-brand-700 active:scale-95 text-white font-bold text-sm shadow-md shadow-brand-500/20 transition-all cursor-pointer shrink-0"
        >
          <PlusCircle className="w-4 h-4" />
          <span>{t.startNewRequestBtn}</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
        <button
          type="button"
          onClick={() => setFilter('all')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
            filter === 'all'
              ? 'bg-brand-100 text-brand-800'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          {t.filterAll} ({cases.length})
        </button>
        <button
          type="button"
          onClick={() => setFilter('active')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
            filter === 'active'
              ? 'bg-brand-100 text-brand-800'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          {t.filterActive} ({cases.filter((c) => c.status !== 'COMPLETED' && c.status !== 'CANCELLED').length})
        </button>
        <button
          type="button"
          onClick={() => setFilter('completed')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
            filter === 'completed'
              ? 'bg-brand-100 text-brand-800'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          {t.filterCompleted} ({cases.filter((c) => c.status === 'COMPLETED').length})
        </button>
      </div>

      {/* Cases List or Empty State */}
      {filteredCases.length === 0 ? (
        <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-8 sm:p-12 text-center">
          <div className="w-14 h-14 mx-auto mb-3 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
            <Inbox className="w-7 h-7" />
          </div>
          <h3 className="text-base sm:text-lg font-bold text-slate-800 mb-1">
            {t.noCasesTitle}
          </h3>
          <p className="text-xs sm:text-sm text-slate-500 max-w-md mx-auto mb-5">
            {t.noCasesDesc}
          </p>
          <button
            type="button"
            onClick={onStartNewRequest}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs shadow transition-all cursor-pointer"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            {t.startNewRequestBtn}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredCases.map((caseItem) => (
            <div
              key={caseItem.caseId}
              onClick={() => onOpenCase(caseItem)}
              className="group bg-white rounded-2xl p-5 border border-slate-200 hover:border-brand-500/50 shadow-xs hover:shadow-md transition-all cursor-pointer relative overflow-hidden"
            >
              {/* Top Row: Urgency Tag + Status Badge */}
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1 text-[11px] font-black uppercase tracking-wider px-2.5 py-0.5 rounded-full ${
                      caseItem.requestedUrgency === 'emergency'
                        ? 'bg-rose-100 text-rose-800 border border-rose-300'
                        : caseItem.requestedUrgency === 'urgent'
                        ? 'bg-amber-100 text-amber-900 border border-amber-300'
                        : 'bg-slate-100 text-slate-700 border border-slate-300'
                    }`}
                  >
                    {caseItem.requestedUrgency === 'emergency' && <AlertTriangle className="w-3 h-3 text-rose-600" />}
                    {caseItem.requestedUrgency}
                  </span>
                  <span className="text-xs font-mono font-semibold text-slate-400">
                    #{caseItem.caseId.substring(0, 14)}
                  </span>
                </div>

                <StatusBadge status={caseItem.status} language={language} />
              </div>

              {/* Chief Complaint */}
              <h3 className="text-sm sm:text-base font-bold text-slate-900 mb-2 group-hover:text-brand-700 transition-colors line-clamp-2">
                {caseItem.chiefComplaint}
              </h3>

              {/* Details Meta Row */}
              <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 pt-2 border-t border-slate-100">
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  Duration: {caseItem.duration}
                </span>

                <span className="flex items-center gap-1">
                  <FileText className="w-3.5 h-3.5 text-slate-400" />
                  Documents: {caseItem.documentCount}
                </span>

                {caseItem.assignedClinicianName && (
                  <span className="flex items-center gap-1 text-teal-800 font-semibold">
                    <ShieldCheck className="w-3.5 h-3.5 text-teal-600" />
                    {caseItem.assignedClinicianName}
                  </span>
                )}

                <div className="ml-auto flex items-center gap-1 text-brand-600 font-bold text-xs group-hover:translate-x-0.5 transition-transform">
                  <span>{t.actionView}</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
