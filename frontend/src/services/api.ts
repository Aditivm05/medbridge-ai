import { authService } from './authService';

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

export async function authenticatedFetch(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const token = authService.getToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  return fetch(url, {
    ...options,
    headers,
  });
}

export const api = {
  // Auth
  getMyProfile: async () => {
    const res = await authenticatedFetch('/auth/me');
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.json()).detail}`);
    return res.json();
  },

  // Cases
  createCase: async (payload: any) => {
    const res = await authenticatedFetch('/cases', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.json()).detail}`);
    return res.json();
  },

  getCase: async (caseId: string) => {
    const res = await authenticatedFetch(`/cases/${caseId}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(`HTTP ${res.status}: ${err.detail || 'Could not fetch case'}`);
    }
    return res.json();
  },

  listCases: async (patientId?: string, clinicianId?: string) => {
    const params = new URLSearchParams();
    if (patientId) params.set('patientId', patientId);
    if (clinicianId) params.set('clinicianId', clinicianId);
    const query = params.toString() ? `?${params.toString()}` : '';
    const res = await authenticatedFetch(`/cases${query}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  acceptCase: async (caseId: string) => {
    const res = await authenticatedFetch(`/cases/${caseId}/accept`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(`HTTP ${res.status}: ${err.detail}`);
    }
    return res.json();
  },
};
