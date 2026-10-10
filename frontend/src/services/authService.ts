import { UserRole } from '../types';

export interface UserAuthSession {
  uid: string;
  email: string;
  displayName: string;
  role: UserRole;
  isVerifiedClinician: boolean;
  token: string;
}

export const DEMO_AUTH_USERS: Record<string, UserAuthSession> = {
  patient_1: {
    uid: 'patient_demo_1',
    email: 'ananya.sharma@example.com',
    displayName: 'Ananya Sharma (Patient)',
    role: 'patient',
    isVerifiedClinician: false,
    token: 'mock-token-patient-1',
  },
  patient_2: {
    uid: 'patient_demo_2',
    email: 'vikram.joshi@example.com',
    displayName: 'Vikram Joshi (Patient 2)',
    role: 'patient',
    isVerifiedClinician: false,
    token: 'mock-token-patient-2',
  },
  clinician_verified: {
    uid: 'clinician_verified_1',
    email: 'rajesh.patil.md@example.com',
    displayName: 'Dr. Rajesh Patil [DEMO / SIMULATED]',
    role: 'clinician',
    isVerifiedClinician: true,
    token: 'mock-token-clinician-verified',
  },
  clinician_unverified: {
    uid: 'clinician_unverified_2',
    email: 'pending.doctor@example.com',
    displayName: 'Dr. Pending Verification [DEMO / SIMULATED]',
    role: 'clinician',
    isVerifiedClinician: false,
    token: 'mock-token-clinician-unverified',
  },
  admin: {
    uid: 'admin_demo_1',
    email: 'security.admin@medbridge.ai',
    displayName: 'Security Auditor (Admin)',
    role: 'admin',
    isVerifiedClinician: false,
    token: 'mock-token-admin',
  },
};

class AuthService {
  private currentSession: UserAuthSession = DEMO_AUTH_USERS.patient_1;
  private listeners: Set<() => void> = new Set();

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn());
  }

  public getCurrentSession(): UserAuthSession {
    return this.currentSession;
  }

  public getToken(): string {
    return this.currentSession.token;
  }

  public switchUser(userKey: keyof typeof DEMO_AUTH_USERS): void {
    if (DEMO_AUTH_USERS[userKey]) {
      this.currentSession = DEMO_AUTH_USERS[userKey];
      this.notify();
    }
  }

  public switchRole(role: UserRole): void {
    if (role === 'patient') {
      this.switchUser('patient_1');
    } else if (role === 'clinician') {
      this.switchUser('clinician_verified');
    } else if (role === 'admin') {
      this.switchUser('admin');
    }
  }
}

export const authService = new AuthService();
