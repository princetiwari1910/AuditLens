/** Typed API client for AuditLens backend. */

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface HealthResponse {
  status: string;
  provider_mode: string;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export default { getHealth };
