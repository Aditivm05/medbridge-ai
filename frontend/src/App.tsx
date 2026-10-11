import React, { useState, useEffect } from 'react';
import { Header } from './components/common/Header';
import { EmergencyBanner } from './components/common/EmergencyBanner';
import { SimulationBadge } from './components/common/SimulationBadge';
import { LanguageCode, UserRole, ScreenView, CaseData } from './types';
import { getTranslation } from './i18n/translations';
import { useCaseStore } from './services/caseStore';
import { authService, UserAuthSession } from './services/authService';
import { api, API_BASE_URL } from './services/api';

// All 7 Core Screen Components
import { PatientDashboard } from './components/screens/PatientDashboard';
import { IntakeScreen } from './components/screens/IntakeScreen';
import { DocumentUploadScreen } from './components/screens/DocumentUploadScreen';
import { DoctorBriefReviewScreen } from './components/screens/DoctorBriefReviewScreen';
import { ClinicianDashboard } from './components/screens/ClinicianDashboard';
import { ConsultationWorkspace } from './components/screens/ConsultationWorkspace';
import { FollowUpScreen } from './components/screens/FollowUpScreen';

import {
  Server,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ChevronRight,
  Shield,
  Lock,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';

export function App() {
  const [language, setLanguage] = useState<LanguageCode>('en');
  const [role, setRole] = useState<UserRole>('patient');
  const [connectionStatus, setConnectionStatus] = useState<'online' | 'offline' | 'emulators'>('emulators');
  const [backendHealth, setBackendHealth] = useState<any>(null);
  const [isLoadingHealth, setIsLoadingHealth] = useState(false);
  const [authSession, setAuthSession] = useState<UserAuthSession>(authService.getCurrentSession());

  // Security Test Feedback State
  const [securityTestResult, setSecurityTestResult] = useState<{
    testName: string;
    statusCode: number;
    detail: string;
    isPass: boolean;
  } | null>(null);
  const [isTestingSecurity, setIsTestingSecurity] = useState(false);

  // Subscribe to Auth Service updates
  useEffect(() => {
    return authService.subscribe(() => {
      const sess = authService.getCurrentSession();
      setAuthSession(sess);
      setRole(sess.role);
    });
  }, []);

  // Reactive store hook for cases, active case, and screens
  const {
    cases,
    activeCase,
    currentScreen,
    isLoadingPatientCases,
    patientCasesError,
    loadPatientCases,
    navigateTo,
    setActiveCaseId,
    createCase,
    attachDocument,
    patientReviewBrief,
    claimCaseAtomic,
    declineCase,
    syncMatchingPool,
    recordConsultationNotes,
    completeCaseAndFollowUp,
    resetToSyntheticDefaults,
  } = useCaseStore();

  const t = getTranslation(language);

  // Poll or check backend health using configured API base URL
  const checkBackendHealth = async () => {
    setIsLoadingHealth(true);
    try {
      const data = await api.checkHealth();
      setBackendHealth(data);
      setConnectionStatus('emulators');
    } catch {
      setBackendHealth({ status: 'mock_mode', detail: 'Local mock & synthetic engine active' });
      setConnectionStatus('emulators');
    } finally {
      setIsLoadingHealth(false);
    }
  };

  useEffect(() => {
    checkBackendHealth();
  }, []);

  // Fetch patient cases from backend whenever patient session or persona changes
  useEffect(() => {
    if (authSession.role === 'patient') {
      loadPatientCases().catch(() => {});
    }
  }, [authSession.uid, authSession.role]);

  // Live Security & Access Control Tests
  const runSecurityTest = async (testType: 'cross_patient' | 'unverified_clinician' | 'verified_clinician') => {
    setIsTestingSecurity(true);
    setSecurityTestResult(null);

    try {
      // Ensure a live test case owned by patient_demo_1 exists on backend
      const initRes = await fetch(`${API_BASE_URL}/cases`, {
        method: 'POST',
        headers: {
          Authorization: 'Bearer mock-token-patient-1',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chiefComplaint: 'Acute urgent case for security & RBAC boundary verification',
          duration: '3 hours',
          requestedUrgency: 'urgent',
          patientLanguage: 'en',
          idempotencyKey: `idem_sec_test_${Date.now()}`,
        }),
      });
      const targetCase = await initRes.json();
      const testCaseId = targetCase.caseId;

      if (testType === 'cross_patient') {
        // Patient 2 attempts to read Patient 1's case
        const res = await fetch(`${API_BASE_URL}/cases/${testCaseId}`, {
          headers: {
            Authorization: 'Bearer mock-token-patient-2',
          },
        });
        const data = await res.json();
        setSecurityTestResult({
          testName: 'Cross-Patient Ownership Boundary Check',
          statusCode: res.status,
          detail: data.detail || JSON.stringify(data),
          isPass: res.status === 403, // 403 is the REQUIRED secure response
        });
      } else if (testType === 'unverified_clinician') {
        // Enqueue case to matching pool first
        await fetch(`${API_BASE_URL}/cases/${testCaseId}/submit`, {
          method: 'POST',
          headers: { Authorization: 'Bearer mock-token-patient-1' },
        });
        await fetch(`${API_BASE_URL}/cases/${testCaseId}/matching`, {
          method: 'POST',
          headers: { Authorization: 'Bearer mock-token-patient-1' },
        });

        // Unverified clinician attempts to accept case
        const res = await fetch(`${API_BASE_URL}/cases/${testCaseId}/accept`, {
          method: 'POST',
          headers: {
            Authorization: 'Bearer mock-token-clinician-unverified',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({}),
        });
        const data = await res.json();
        setSecurityTestResult({
          testName: 'Unverified Clinician Claim Block',
          statusCode: res.status,
          detail: data.detail || JSON.stringify(data),
          isPass: res.status === 403, // 403 is the REQUIRED secure response
        });
      } else if (testType === 'verified_clinician') {
        // Verified clinician profile & claim check
        const res = await fetch(`${API_BASE_URL}/auth/me`, {
          headers: {
            Authorization: 'Bearer mock-token-clinician-verified',
          },
        });
        const data = await res.json();
        setSecurityTestResult({
          testName: 'Verified Clinician Claims Inspection',
          statusCode: res.status,
          detail: `User: ${data.displayName} | Role: ${data.role} | Verified Clinician: ${data.isVerifiedClinician}`,
          isPass: res.status === 200 && data.isVerifiedClinician === true,
        });
      }
    } catch (err: any) {
      setSecurityTestResult({
        testName: 'Network Test Error',
        statusCode: 500,
        detail: `Could not connect to FastAPI server at ${API_BASE_URL}: ${err.message}`,
        isPass: false,
      });
    } finally {
      setIsTestingSecurity(false);
    }
  };

  const effectiveCase: CaseData = activeCase || cases[0];

  const handleOpenCase = (caseItem: CaseData) => {
    setActiveCaseId(caseItem.caseId);
    if (caseItem.status === 'DRAFT') {
      navigateTo('upload', caseItem.caseId);
    } else if (caseItem.status === 'SUBMITTED' || caseItem.status === 'MATCHING') {
      navigateTo('brief-review', caseItem.caseId);
    } else if (caseItem.status === 'ACCEPTED' || caseItem.status === 'IN_CONSULTATION') {
      authService.switchRole('clinician');
      navigateTo('consultation', caseItem.caseId);
    } else if (caseItem.status === 'COMPLETED') {
      navigateTo('follow-up', caseItem.caseId);
    } else {
      navigateTo('brief-review', caseItem.caseId);
    }
  };

  const workflowSteps: { id: ScreenView; label: string; roleTarget?: UserRole }[] = [
    { id: 'patient-dashboard', label: '1. Dashboard', roleTarget: 'patient' },
    { id: 'intake', label: '2. Intake', roleTarget: 'patient' },
    { id: 'upload', label: '3. Upload', roleTarget: 'patient' },
    { id: 'brief-review', label: '4. Doctor Brief', roleTarget: 'patient' },
    { id: 'clinician-dashboard', label: '5. Clinician Pool', roleTarget: 'clinician' },
    { id: 'consultation', label: '6. Consultation', roleTarget: 'clinician' },
    { id: 'follow-up', label: '7. Follow-Up', roleTarget: 'patient' },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 font-sans text-slate-800 antialiased selection:bg-brand-500 selection:text-white">
      {/* Universal Top Header with Persona Selector & Auth Claims */}
      <Header
        currentLanguage={language}
        onLanguageChange={setLanguage}
        currentRole={role}
        onRoleChange={(newRole) => {
          authService.switchRole(newRole);
          if (newRole === 'patient') {
            navigateTo('patient-dashboard');
          } else if (newRole === 'clinician') {
            navigateTo('clinician-dashboard');
          }
        }}
        currentScreen={currentScreen}
        onNavigate={(screen) => navigateTo(screen)}
        connectionStatus={connectionStatus}
        activeAuthUser={authSession}
        onSwitchAuthUser={(userKey) => authService.switchUser(userKey)}
      />

      {/* Golden Workflow Stepper / Interactive Demo Bar */}
      <div className="bg-white border-b border-slate-200 px-4 py-2.5 overflow-x-auto shadow-2xs">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="font-bold text-slate-400 uppercase tracking-wider text-[10px]">
              Workflow:
            </span>
            <div className="flex items-center gap-1">
              {workflowSteps.map((step, idx) => {
                const isActive = currentScreen === step.id;
                return (
                  <React.Fragment key={step.id}>
                    <button
                      type="button"
                      onClick={() => {
                        if (step.roleTarget) authService.switchRole(step.roleTarget);
                        navigateTo(step.id);
                      }}
                      className={`px-2.5 py-1 rounded-lg font-bold text-[11px] transition-all cursor-pointer whitespace-nowrap ${
                        isActive
                          ? 'bg-brand-600 text-white shadow-xs scale-102'
                          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                      }`}
                    >
                      {step.label}
                    </button>
                    {idx < workflowSteps.length - 1 && (
                      <ChevronRight className="w-3 h-3 text-slate-300 shrink-0" />
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              resetToSyntheticDefaults();
              authService.switchRole('patient');
            }}
            className="hidden sm:inline-flex items-center gap-1 text-[11px] font-bold text-slate-500 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 px-2.5 py-1 rounded-lg border border-slate-200 cursor-pointer shrink-0 transition-colors"
            title="Reset synthetic state back to defaults"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Reset Demo</span>
          </button>
        </div>
      </div>

      {/* Main Content Viewport */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6 sm:py-8">
        {/* NON-NEGOTIABLE SAFETY RULE: Static Immediate Emergency Guidance */}
        {effectiveCase?.requestedUrgency === 'emergency' && currentScreen !== 'intake' && (
          <EmergencyBanner language={language} />
        )}

        {/* Global Coordination Platform Notice */}
        <div className="bg-teal-50 border border-teal-200 rounded-xl p-3 mb-6 text-xs text-teal-950 flex items-start gap-2.5 shadow-2xs">
          <ShieldAlert className="w-4 h-4 text-teal-700 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <span className="font-bold">{t.coordinationNotice}</span> All simulated consultations and demo doctors are labeled{' '}
            <span className="font-mono font-bold text-amber-900 bg-amber-100 px-1 py-0.2 rounded">
              [DEMO / SIMULATED]
            </span>
            .
          </div>
        </div>

        {/* Dynamic Screen View Router */}
        {currentScreen === 'patient-dashboard' && (
          <PatientDashboard
            cases={cases}
            language={language}
            isLoading={isLoadingPatientCases}
            error={patientCasesError}
            onRefreshCases={() => {
              loadPatientCases().catch(() => {});
            }}
            onStartNewRequest={() => navigateTo('intake')}
            onOpenCase={handleOpenCase}
          />
        )}

        {currentScreen === 'intake' && (
          <IntakeScreen
            language={language}
            onBack={() => navigateTo('patient-dashboard')}
            onSubmitIntake={async (intakeData) => {
              const newCase = await createCase(intakeData);
              navigateTo('upload', newCase.caseId);
            }}
          />
        )}

        {currentScreen === 'upload' && effectiveCase && (
          <DocumentUploadScreen
            currentCase={effectiveCase}
            language={language}
            onBack={() => navigateTo('intake')}
            onAttachDocument={(doc) => attachDocument(effectiveCase.caseId, doc)}
            onProceedToBrief={() => {
              navigateTo('brief-review', effectiveCase.caseId);
            }}
          />
        )}

        {currentScreen === 'brief-review' && effectiveCase && (
          <DoctorBriefReviewScreen
            currentCase={effectiveCase}
            language={language}
            onBack={() => navigateTo('upload', effectiveCase.caseId)}
            onApproveAndEnqueue={() => {
              patientReviewBrief(effectiveCase.caseId, true);
              authService.switchRole('clinician');
              navigateTo('clinician-dashboard', effectiveCase.caseId);
            }}
            onSaveCorrections={(corrections) => {
              patientReviewBrief(effectiveCase.caseId, false, corrections);
            }}
          />
        )}

        {currentScreen === 'clinician-dashboard' && (
          <ClinicianDashboard
            cases={cases}
            language={language}
            onClaimCase={async (caseId, clinicianId, simulateConflict) => {
              const result = await claimCaseAtomic(caseId, clinicianId, simulateConflict);
              if (result.success) {
                navigateTo('consultation', caseId);
              }
              return result;
            }}
            onDeclineCase={async (caseId, reason) => {
              return await declineCase(caseId, reason);
            }}
            onOpenConsultation={(caseItem) => {
              setActiveCaseId(caseItem.caseId);
              navigateTo('consultation', caseItem.caseId);
            }}
            onRefreshPool={async () => {
              await syncMatchingPool();
            }}
          />
        )}

        {currentScreen === 'consultation' && effectiveCase && (
          <ConsultationWorkspace
            currentCase={effectiveCase}
            language={language}
            onBack={() => navigateTo('clinician-dashboard')}
            onSaveConsultation={async (notes, careAdvice) => {
              await recordConsultationNotes(effectiveCase.caseId, notes, careAdvice);
              navigateTo('follow-up', effectiveCase.caseId);
            }}
          />
        )}

        {currentScreen === 'follow-up' && effectiveCase && (
          <FollowUpScreen
            currentCase={effectiveCase}
            language={language}
            onBack={() => navigateTo('consultation', effectiveCase.caseId)}
            onFinalizeCase={async (followUpData) => {
              await completeCaseAndFollowUp(effectiveCase.caseId, followUpData);
              authService.switchRole('patient');
              navigateTo('patient-dashboard');
            }}
          />
        )}

        {/* Phase 4 Live Security & RBAC Enforcement Inspector (Development Only) */}
        {import.meta.env.DEV && (
          <div className="mt-8 bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100 mb-4">
              <div className="flex items-center gap-2">
                <Shield className="w-5 h-5 text-teal-600" />
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Phase 4 Live Security & RBAC Enforcement Tester (Dev Mode)
                  </h3>
                  <p className="text-xs text-slate-500">
                    Verify ownership boundaries and unverified clinician restrictions against the FastAPI server.
                  </p>
                </div>
              </div>
              <span className="text-[11px] font-mono font-bold bg-teal-100 text-teal-800 px-2.5 py-1 rounded-lg">
                Token: {authSession.token}
              </span>
            </div>

            <div className="flex flex-wrap gap-2.5 mb-4">
              <button
                type="button"
                onClick={() => runSecurityTest('cross_patient')}
                disabled={isTestingSecurity}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-slate-800 border border-slate-200 transition-all cursor-pointer disabled:opacity-50"
              >
                <Lock className="w-3.5 h-3.5 text-rose-600" />
                <span>Test 1: Cross-Patient Read (Expect 403 Forbidden)</span>
              </button>

              <button
                type="button"
                onClick={() => runSecurityTest('unverified_clinician')}
                disabled={isTestingSecurity}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-slate-800 border border-slate-200 transition-all cursor-pointer disabled:opacity-50"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                <span>Test 2: Unverified Clinician Claim (Expect 403 Forbidden)</span>
              </button>

              <button
                type="button"
                onClick={() => runSecurityTest('verified_clinician')}
                disabled={isTestingSecurity}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-slate-800 border border-slate-200 transition-all cursor-pointer disabled:opacity-50"
              >
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>Test 3: Verified Clinician Claims (Expect 200 OK)</span>
              </button>
            </div>

            {/* Test Result Display */}
            {securityTestResult && (
              <div
                className={`p-3.5 rounded-xl border text-xs ${
                  securityTestResult.isPass
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-950'
                    : 'bg-rose-50 border-rose-300 text-rose-950'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold flex items-center gap-1.5">
                    {securityTestResult.isPass ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-rose-600" />
                    )}
                    {securityTestResult.testName}
                  </span>
                  <span className="font-mono font-bold px-2 py-0.5 rounded bg-white border">
                    HTTP {securityTestResult.statusCode}
                  </span>
                </div>
                <p className="font-mono text-[11px] mt-1 text-slate-700 bg-white/70 p-2 rounded border border-slate-200">
                  {securityTestResult.detail}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Backend & Emulator Health Telemetry Widget */}
        <div className="mt-6 bg-white rounded-2xl border border-slate-200 p-4 sm:p-5 shadow-2xs">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
              <Server className="w-3.5 h-3.5 text-brand-600" />
              Backend & Cloud Emulator Telemetry
            </span>
            <div className="flex items-center gap-2">
              <SimulationBadge size="sm" />
              <button
                type="button"
                onClick={checkBackendHealth}
                className="text-xs text-brand-600 hover:text-brand-800 font-semibold flex items-center gap-1 cursor-pointer"
              >
                <RefreshCw className={`w-3 h-3 ${isLoadingHealth ? 'animate-spin' : ''}`} />
                <span>Ping Health</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs font-mono">
            <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-400 block text-[10px]">FASTAPI HEALTH</span>
              <span className="font-bold text-emerald-600 flex items-center gap-1 mt-0.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping inline-block" />
                {backendHealth?.status || 'healthy'}
              </span>
            </div>
            <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-400 block text-[10px]">AI MODEL</span>
              <span className="text-slate-700 font-semibold mt-0.5 block">
                {backendHealth?.aiModel || 'gemini-2.0-flash'}
              </span>
            </div>
            <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-400 block text-[10px]">AUTH HOST</span>
              <span className="text-slate-700 font-semibold mt-0.5 block">
                {backendHealth?.emulators?.auth || '127.0.0.1:9099'}
              </span>
            </div>
            <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100">
              <span className="text-slate-400 block text-[10px]">FIRESTORE HOST</span>
              <span className="text-slate-700 font-semibold mt-0.5 block">
                {backendHealth?.emulators?.firestore || '127.0.0.1:8080'}
              </span>
            </div>
          </div>
        </div>
      </main>

      {/* Accessible Footer */}
      <footer className="mt-auto border-t border-slate-200 bg-white py-4 px-4 text-center text-xs text-slate-500">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>
            MedBridge AI &bull; Care Coordination Architecture MVP &bull;{' '}
            <strong className="text-amber-800">[DEMO / SIMULATED]</strong>
          </span>
          <span className="text-slate-400 text-[11px]">
            National Emergency: Call 112 (India) &bull; Accessible Typography (WCAG AA)
          </span>
        </div>
      </footer>
    </div>
  );
}
