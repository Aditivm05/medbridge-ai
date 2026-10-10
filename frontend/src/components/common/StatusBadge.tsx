import React from 'react';
import { CaseStatus, LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';

interface StatusBadgeProps {
  status: CaseStatus;
  language: LanguageCode;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, language }) => {
  const t = getTranslation(language);

  const config: Record<CaseStatus, { label: string; bg: string; text: string; dot: string }> = {
    DRAFT: {
      label: t.statusDraft,
      bg: 'bg-slate-100 border-slate-200',
      text: 'text-slate-700',
      dot: 'bg-slate-400',
    },
    SUBMITTED: {
      label: t.statusSubmitted,
      bg: 'bg-blue-50 border-blue-200',
      text: 'text-blue-700',
      dot: 'bg-blue-500 animate-pulse',
    },
    MATCHING: {
      label: t.statusMatching,
      bg: 'bg-purple-50 border-purple-200',
      text: 'text-purple-700',
      dot: 'bg-purple-500 animate-ping',
    },
    ACCEPTED: {
      label: t.statusAccepted,
      bg: 'bg-amber-50 border-amber-200',
      text: 'text-amber-800',
      dot: 'bg-amber-500',
    },
    IN_CONSULTATION: {
      label: t.statusInConsultation,
      bg: 'bg-teal-50 border-teal-200',
      text: 'text-teal-800',
      dot: 'bg-teal-500 animate-pulse',
    },
    COMPLETED: {
      label: t.statusCompleted,
      bg: 'bg-emerald-50 border-emerald-200',
      text: 'text-emerald-800',
      dot: 'bg-emerald-500',
    },
    CANCELLED: {
      label: t.statusCancelled,
      bg: 'bg-rose-50 border-rose-200',
      text: 'text-rose-700',
      dot: 'bg-rose-400',
    },
    NO_CLINICIAN_AVAILABLE: {
      label: 'No Clinician Available',
      bg: 'bg-orange-50 border-orange-200',
      text: 'text-orange-700',
      dot: 'bg-orange-400',
    },
    FAILED: {
      label: 'Failed',
      bg: 'bg-rose-50 border-rose-200',
      text: 'text-rose-700',
      dot: 'bg-rose-400',
    },
    ESCALATED: {
      label: 'Escalated to Hospital',
      bg: 'bg-rose-100 border-rose-300',
      text: 'text-rose-900',
      dot: 'bg-rose-600 animate-bounce',
    },
  };

  const current = config[status] || config.DRAFT;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold border tracking-wide uppercase select-none ${current.bg} ${current.text}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${current.dot}`} />
      {current.label}
    </span>
  );
};
