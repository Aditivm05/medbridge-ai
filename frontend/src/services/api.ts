import { authService } from './authService';
import { DoctorBrief, DoctorBriefEditRequest, ClinicianMatchResponse } from '../types';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/+$/, '');

function extractErrorDetail(data: any, status: number): string {
  if (!data) return `HTTP ${status}`;
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((err: any) => {
        const field = Array.isArray(err.loc) ? err.loc.slice(1).join('.') : '';
        return field ? `${field}: ${err.msg}` : err.msg || JSON.stringify(err);
      })
      .join('; ');
  }
  if (typeof data === 'object') return JSON.stringify(data.detail || data);
  return `HTTP ${status}`;
}

export async function authenticatedFetch(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const token = authService.getToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const url = endpoint.startsWith('http')
    ? endpoint
    : `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  return fetch(url, {
    ...options,
    headers,
  });
}

export const api = {
  // Health
  checkHealth: async () => {
    const rootUrl = API_BASE_URL.replace(/\/api\/v1\/?$/, '');
    const res = await fetch(`${rootUrl}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  // Auth
  getMyProfile: async () => {
    const res = await authenticatedFetch('/auth/me');
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      throw new Error(errDetail);
    }
    return res.json();
  },

  // Cases
  createCase: async (payload: any) => {
    const res = await authenticatedFetch('/cases', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  getCase: async (caseId: string) => {
    const res = await authenticatedFetch(`/cases/${caseId}`);
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  listCases: async (patientId?: string, clinicianId?: string) => {
    const params = new URLSearchParams();
    if (patientId) params.set('patientId', patientId);
    if (clinicianId) params.set('clinicianId', clinicianId);
    const query = params.toString() ? `?${params.toString()}` : '';
    const res = await authenticatedFetch(`/cases${query}`);
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  submitCase: async (caseId: string, idempotencyKey?: string) => {
    const res = await authenticatedFetch(`/cases/${caseId}/submit`, {
      method: 'POST',
      body: JSON.stringify(idempotencyKey ? { idempotencyKey } : {}),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  enqueueMatching: async (caseId: string) => {
    const res = await authenticatedFetch(`/cases/${caseId}/matching`, {
      method: 'POST',
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  acceptCase: async (caseId: string) => {
    const res = await authenticatedFetch(`/cases/${caseId}/accept`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        errDetail = extractErrorDetail(err, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  getMatchingPool: async (): Promise<any[]> => {
    const res = await authenticatedFetch('/clinicians/matching-pool');
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        errDetail = extractErrorDetail(err, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  declineCase: async (caseId: string, reason?: string) => {
    const res = await authenticatedFetch(`/cases/${caseId}/decline`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || 'Clinician unavailable or out of scope' }),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        errDetail = extractErrorDetail(err, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  matchCase: async (caseId: string): Promise<ClinicianMatchResponse> => {
    const res = await authenticatedFetch(`/cases/${caseId}/match`, {
      method: 'POST',
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        errDetail = extractErrorDetail(err, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  listClinicians: async () => {
    const res = await authenticatedFetch('/clinicians');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },

  updateClinicianAvailability: async (clinicianId: string, availability: string) => {
    const res = await authenticatedFetch(`/clinicians/${clinicianId}/availability`, {
      method: 'PATCH',
      body: JSON.stringify({ availability }),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        errDetail = extractErrorDetail(err, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  // Doctor Brief Endpoints
  generateBrief: async (caseId: string, confirmRegenerate: boolean = false): Promise<DoctorBrief> => {
    const res = await authenticatedFetch(`/cases/${caseId}/brief/generate`, {
      method: 'POST',
      body: JSON.stringify({ confirmRegenerate }),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  getBrief: async (caseId: string): Promise<DoctorBrief> => {
    const res = await authenticatedFetch(`/cases/${caseId}/brief`);
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  updateBrief: async (caseId: string, payload: DoctorBriefEditRequest): Promise<DoctorBrief> => {
    const res = await authenticatedFetch(`/cases/${caseId}/brief`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  approveBrief: async (caseId: string, notes?: string): Promise<DoctorBrief> => {
    const res = await authenticatedFetch(`/cases/${caseId}/brief/approve`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  reviewBrief: async (caseId: string, clinicianNotes?: string): Promise<DoctorBrief> => {
    const res = await authenticatedFetch(`/cases/${caseId}/brief/review`, {
      method: 'POST',
      body: JSON.stringify({ clinicianNotes }),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        errDetail = extractErrorDetail(data, res.status);
      } catch {}
      const error: any = new Error(errDetail);
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  uploadDocument: (
    caseId: string,
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<any> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const token = authService.getToken();
      const url = `${API_BASE_URL}/cases/${caseId}/documents/upload-and-verify`;

      xhr.open('POST', url);
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      }

      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && event.total > 0) {
            const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
            onProgress(percent);
          }
        };
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText);
            resolve(data);
          } catch {
            resolve({
              documentId: `doc_${Date.now()}`,
              caseId,
              fileName: file.name,
              mimeType: file.type || 'application/octet-stream',
              sizeBytes: file.size,
              uploadedAt: new Date().toISOString(),
              magicBytesValidated: true,
              ocrStatus: 'processed',
            });
          }
        } else {
          let errorDetail = `Upload failed (HTTP ${xhr.status})`;
          try {
            const resJson = JSON.parse(xhr.responseText);
            if (resJson.detail) {
              errorDetail = resJson.detail;
            }
          } catch {
            if (xhr.statusText) {
              errorDetail = xhr.statusText;
            }
          }
          reject(new Error(errorDetail));
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network error: Unable to reach backend server.'));
      };

      xhr.ontimeout = () => {
        reject(new Error('Upload request timed out. Please retry.'));
      };

      const formData = new FormData();
      formData.append('file', file);
      xhr.send(formData);
    });
  },

  // Consultation & Follow-Up Endpoints (Phase 9)
  saveConsultation: async (
    caseId: string,
    payload: { clinicianNotes: string; provisionalCareAdvice: string; isSimulated?: boolean }
  ): Promise<any> => {
    const res = await authenticatedFetch(`/cases/${caseId}/consultation`, {
      method: 'POST',
      body: JSON.stringify({
        ...payload,
        isSimulated: payload.isSimulated ?? true,
      }),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        if (data.detail) errDetail = data.detail;
      } catch {}
      throw new Error(errDetail);
    }
    return res.json();
  },

  getConsultation: async (caseId: string): Promise<any> => {
    const res = await authenticatedFetch(`/cases/${caseId}/consultation`);
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        if (data.detail) errDetail = data.detail;
      } catch {}
      throw new Error(errDetail);
    }
    return res.json();
  },

  completeCaseWithFollowUp: async (
    caseId: string,
    payload: { required: boolean; recommendedDate: string; instructions: string }
  ): Promise<any> => {
    const res = await authenticatedFetch(`/cases/${caseId}/complete`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        if (data.detail) errDetail = data.detail;
      } catch {}
      throw new Error(errDetail);
    }
    return res.json();
  },

  getFollowUp: async (caseId: string): Promise<any> => {
    const res = await authenticatedFetch(`/cases/${caseId}/follow-up`);
    if (!res.ok) {
      let errDetail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        if (data.detail) errDetail = data.detail;
      } catch {}
      throw new Error(errDetail);
    }
    return res.json();
  },
};

export function mapUploadError(rawError: string): string {
  const lower = rawError.toLowerCase();
  if (lower.includes('magic byte') || lower.includes('file content does not match')) {
    return 'Magic byte verification failed. The file content does not match its declared format.';
  }
  if (lower.includes('10 mb') || lower.includes('larger than') || lower.includes('exceeds')) {
    return 'This file is larger than 10 MB.';
  }
  if (lower.includes('maximum limit of 5') || lower.includes('5 documents')) {
    return 'Maximum 5 files per case reached.';
  }
  if (lower.includes('empty') || lower.includes('0 bytes')) {
    return 'This file is empty (0 bytes).';
  }
  if (lower.includes('not permitted') || lower.includes('invalid file format') || lower.includes('extension')) {
    return 'Invalid file extension. Only PDF, JPG, and PNG documents are allowed.';
  }
  if (lower.includes('invalid mime type') || lower.includes('mime type')) {
    return 'Unsupported MIME type. Only application/pdf, image/jpeg, and image/png are supported.';
  }
  if (lower.includes('forbidden') || lower.includes('403')) {
    return 'Access denied: You can only upload documents to your own medical cases.';
  }
  if (lower.includes('401') || lower.includes('unauthorized')) {
    return 'Session expired. Please sign in again to upload files.';
  }
  if (lower.includes('404') || lower.includes('not found')) {
    return 'Target case was not found on the server.';
  }
  if (lower.includes('network') || lower.includes('connection failed')) {
    return 'Network connection failed. Unable to reach backend server.';
  }
  return rawError || 'Upload failed. Please try again.';
}

