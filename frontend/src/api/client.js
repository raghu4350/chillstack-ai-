// src/api/client.js
// Axios API client — all calls to FastAPI backend (/api/*)

const BASE = '/api';

async function apiFetch(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Stats
  getStats: () => apiFetch('/stats'),

  // Cases
  getCases: (includeClosed = true) =>
    apiFetch(`/cases?include_closed=${includeClosed}`),
  getCase: (caseId) => apiFetch(`/cases/${caseId}`),

  // Policies
  getPolicies: () => apiFetch('/policies'),
  getPolicy: (id) => apiFetch(`/policies/${id}`),

  // Audit
  getAudit: (caseId = null) =>
    apiFetch(`/audit${caseId ? `?case_id=${caseId}` : ''}`),

  // Analysis
  analyseCase: (caseId) =>
    apiFetch(`/analyse/${caseId}`, { method: 'POST' }),
  analyseCaseOffline: (caseId) =>
    apiFetch(`/analyse/${caseId}/offline`, { method: 'POST' }),

  // Clarification
  addClarification: (caseId, data) =>
    apiFetch(`/cases/${caseId}/clarification`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Record action
  recordAction: (caseId, data) =>
    apiFetch(`/cases/${caseId}/record`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Clear conversation
  clearConversation: (caseId) =>
    apiFetch(`/cases/${caseId}/conversation`, { method: 'DELETE' }),

  // Health
  health: () => apiFetch('/health'),
};
