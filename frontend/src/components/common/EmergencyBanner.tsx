import React from 'react';
import { AlertTriangle, PhoneCall, MapPin } from 'lucide-react';
import { LanguageCode } from '../../types';
import { getTranslation } from '../../i18n/translations';

interface EmergencyBannerProps {
  language: LanguageCode;
}

export const EmergencyBanner: React.FC<EmergencyBannerProps> = ({ language }) => {
  const t = getTranslation(language);

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="w-full bg-emergency-600 text-white rounded-xl shadow-lg border-2 border-emergency-700 p-4 sm:p-5 mb-6 transition-all animate-pulse"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-white/20 rounded-lg shrink-0 mt-0.5">
          <AlertTriangle className="w-6 h-6 text-white" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h2 className="text-base sm:text-lg font-bold tracking-wide uppercase">
              {t.emergencyBannerTitle}
            </h2>
            <span className="text-xs bg-black/40 px-2 py-0.5 rounded font-mono font-semibold">
              STATIC ZERO-NETWORK PROTOCOL
            </span>
          </div>
          <p className="text-sm sm:text-base text-rose-100 leading-relaxed font-medium">
            {t.emergencyBannerDesc}
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <a
              href="tel:112"
              className="inline-flex items-center gap-2 bg-white text-emergency-700 hover:bg-rose-50 px-4 py-2.5 rounded-lg font-bold text-sm sm:text-base shadow active:scale-95 transition-transform"
            >
              <PhoneCall className="w-4 h-4 text-emergency-700" />
              {t.emergencyCallBtn}
            </a>

            <a
              href="https://www.google.com/maps/search/hospital+near+me"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 bg-emergency-800/80 hover:bg-emergency-800 text-white border border-white/30 px-4 py-2.5 rounded-lg font-semibold text-sm sm:text-base active:scale-95 transition-transform"
            >
              <MapPin className="w-4 h-4" />
              {t.nearestHospital}
            </a>
          </div>

          <div className="mt-2.5 text-xs text-rose-200">
            * This system coordinates clinical consultation only. Never wait for an app response during acute emergencies.
          </div>
        </div>
      </div>
    </div>
  );
};
