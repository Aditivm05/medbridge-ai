import React from 'react';
import { Activity, Globe, Home, PlusCircle, Sparkles, Shield } from 'lucide-react';
import { LanguageCode, ScreenView, UserRole } from '../../types';
import { getTranslation } from '../../i18n/translations';
import { SimulationBadge } from './SimulationBadge';
import { ConnectionIndicator } from './ConnectionIndicator';
import { UserAuthSession, DEMO_AUTH_USERS } from '../../services/authService';

interface HeaderProps {
  currentLanguage: LanguageCode;
  onLanguageChange: (lang: LanguageCode) => void;
  currentRole: UserRole;
  onRoleChange: (role: UserRole) => void;
  currentScreen: ScreenView;
  onNavigate: (screen: ScreenView) => void;
  connectionStatus: 'online' | 'offline' | 'emulators';
  activeAuthUser?: UserAuthSession;
  onSwitchAuthUser?: (userKey: keyof typeof DEMO_AUTH_USERS) => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentLanguage,
  onLanguageChange,
  currentRole,
  onRoleChange,
  currentScreen,
  onNavigate,
  connectionStatus,
  activeAuthUser,
  onSwitchAuthUser,
}) => {
  const t = getTranslation(currentLanguage);

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200 shadow-xs">
      <div className="max-w-6xl mx-auto px-4 py-2.5 flex flex-col md:flex-row items-center justify-between gap-3">
        {/* Brand & Connection Badge */}
        <div className="flex items-center justify-between w-full md:w-auto gap-3">
          <div
            onClick={() => onNavigate(currentRole === 'patient' ? 'patient-dashboard' : 'clinician-dashboard')}
            className="flex items-center gap-2.5 cursor-pointer select-none"
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-brand-700 to-brand-500 flex items-center justify-center text-white shadow-md shadow-brand-500/20">
              <Activity className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base sm:text-lg font-black text-slate-900 tracking-tight leading-none">
                  {t.appTitle}
                </span>
                <SimulationBadge />
              </div>
              <p className="text-[10px] text-slate-500 font-medium">
                {t.appSubtitle}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 md:hidden">
            <ConnectionIndicator status={connectionStatus} language={currentLanguage} />
          </div>
        </div>

        {/* Screen Navigation Links */}
        <nav className="flex items-center gap-1 bg-slate-100/80 p-1 rounded-xl border border-slate-200 text-xs font-bold overflow-x-auto max-w-full">
          <button
            type="button"
            onClick={() => onNavigate('patient-dashboard')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
              currentScreen === 'patient-dashboard'
                ? 'bg-white text-brand-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Home className="w-3.5 h-3.5" />
            <span>{t.navDashboard}</span>
          </button>

          <button
            type="button"
            onClick={() => onNavigate('intake')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
              currentScreen === 'intake' || currentScreen === 'upload' || currentScreen === 'brief-review'
                ? 'bg-white text-brand-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>{t.navIntake}</span>
          </button>

          <button
            type="button"
            onClick={() => onNavigate('clinician-dashboard')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
              currentScreen === 'clinician-dashboard' || currentScreen === 'consultation' || currentScreen === 'follow-up'
                ? 'bg-white text-purple-700 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>{t.navClinicianPool}</span>
          </button>
        </nav>

        {/* Right Section: Auth Claims Badge, Persona Selector, Language Select */}
        <div className="flex items-center justify-between md:justify-end w-full md:w-auto gap-2">
          {/* Active Auth Claims Pill */}
          {activeAuthUser && (
            <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 px-2 py-1 rounded-lg text-[11px] font-semibold text-slate-700">
              <Shield className="w-3.5 h-3.5 text-teal-600 shrink-0" />
              <select
                value={
                  activeAuthUser.uid === 'patient_demo_1'
                    ? 'patient_1'
                    : activeAuthUser.uid === 'patient_demo_2'
                    ? 'patient_2'
                    : activeAuthUser.uid === 'clinician_verified_1'
                    ? 'clinician_verified'
                    : activeAuthUser.uid === 'clinician_unverified_2'
                    ? 'clinician_unverified'
                    : 'admin'
                }
                onChange={(e) => {
                  const val = e.target.value as keyof typeof DEMO_AUTH_USERS;
                  if (onSwitchAuthUser) onSwitchAuthUser(val);
                  if (val.startsWith('patient')) {
                    onRoleChange('patient');
                    onNavigate('patient-dashboard');
                  } else if (val.startsWith('clinician')) {
                    onRoleChange('clinician');
                    onNavigate('clinician-dashboard');
                  } else {
                    onRoleChange('admin');
                  }
                }}
                className="bg-transparent border-0 font-bold text-slate-800 focus:ring-0 cursor-pointer outline-hidden pr-2 text-[11px]"
                aria-label="Auth Persona Selector"
              >
                <option value="patient_1">Patient: Ananya (Own Cases)</option>
                <option value="patient_2">Patient: Vikram (Cross-Check)</option>
                <option value="clinician_verified">Doctor: Dr. Patil (Verified)</option>
                <option value="clinician_unverified">Doctor: Dr. Pending (Unverified)</option>
                <option value="admin">Auditor: Admin</option>
              </select>
              {activeAuthUser.isVerifiedClinician && (
                <span className="text-[10px] bg-emerald-100 text-emerald-800 font-bold px-1.5 py-0.2 rounded shrink-0">
                  Verified
                </span>
              )}
              {activeAuthUser.role === 'clinician' && !activeAuthUser.isVerifiedClinician && (
                <span className="text-[10px] bg-amber-100 text-amber-800 font-bold px-1.5 py-0.2 rounded shrink-0">
                  Unverified
                </span>
              )}
            </div>
          )}

          {/* Connection Indicator */}
          <div className="hidden lg:flex">
            <ConnectionIndicator status={connectionStatus} language={currentLanguage} />
          </div>

          {/* Language Selector Dropdown */}
          <div className="flex items-center gap-1 pl-1 border-l border-slate-200">
            <Globe className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={currentLanguage}
              onChange={(e) => onLanguageChange(e.target.value as LanguageCode)}
              className="text-xs font-bold bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded-lg px-2 py-1 focus:ring-2 focus:ring-brand-500 outline-hidden cursor-pointer"
              aria-label="Language selector"
            >
              <option value="en">English (EN)</option>
              <option value="hi">हिन्दी (HI)</option>
              <option value="mr">मराठी (MR)</option>
            </select>
          </div>
        </div>
      </div>
    </header>
  );
};
