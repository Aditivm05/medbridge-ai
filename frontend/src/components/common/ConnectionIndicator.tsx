import React from 'react';
import { Wifi, WifiOff, Database } from 'lucide-react';
import { LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';

interface ConnectionIndicatorProps {
  status: 'online' | 'offline' | 'emulators';
  language: LanguageCode;
}

export const ConnectionIndicator: React.FC<ConnectionIndicatorProps> = ({ status, language }) => {
  const t = getTranslation(language);

  if (status === 'emulators') {
    return (
      <div
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200"
        title="Local Firebase & FastAPI Emulators active (Zero Cloud Cost)"
      >
        <Database className="w-3.5 h-3.5 text-emerald-600 animate-pulse" />
        <span>{t.connStatusEmulators}</span>
      </div>
    );
  }

  if (status === 'online') {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
        <Wifi className="w-3.5 h-3.5 text-emerald-600" />
        <span>{t.connStatusOnline}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-800 border border-rose-200">
      <WifiOff className="w-3.5 h-3.5 text-rose-600" />
      <span>{t.connStatusOffline}</span>
    </div>
  );
};
