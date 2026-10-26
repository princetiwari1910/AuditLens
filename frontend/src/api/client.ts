/** Typed API client for AuditLens backend. */

import type { Audit, Template, Finding } from './types';

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
  });
  if (!res.ok) {
    let errMsg = `API error ${res.status}`;
    try {
      const errJson = await res.json();
      errMsg = errJson.detail || errMsg;
    } catch {
      const body = await res.text();
      if (body) errMsg = body;
    }
    throw new Error(errMsg);
  }
  return res.json() as Promise<T>;
}

export interface HealthResponse {
  status: string;
  provider_mode: string;
}

export interface CostSummary {
  audit_id: string;
  total_calls: number;
  total_cost_usd: number;
  by_provider: Record<string, { calls: number; units: number; cost_usd: number }>;
}

export interface CompareResult {
  before_id: string;
  after_id: string;
  summary: {
    resolved: number;
    new_issue: number;
    still_open: number;
    unchanged_pass: number;
    unsure_change: number;
    added: number;
    removed: number;
  };
  results: Array<{
    rule_id: string;
    status: string;
    before_status: string | null;
    after_status: string | null;
    before_confidence: number | null;
    after_confidence: number | null;
    rule_title: string;
    rationale: string;
    fix_text: string;
  }>;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function getTemplates(): Promise<Template[]> {
  return request<Template[]>('/templates');
}

export function getTemplate(id: string): Promise<Template> {
  return request<Template>(`/templates/${id}`);
}

export function getAudits(): Promise<Audit[]> {
  return request<Audit[]>('/audits');
}

export function getAudit(id: string): Promise<Audit> {
  return request<Audit>(`/audits/${id}`);
}

export async function createAudit(formData: FormData): Promise<{ id: string; status: string }> {
  return request<{ id: string; status: string }>('/audits', {
    method: 'POST',
    body: formData,
  });
}

export async function createDemoAudit(templateId: string = 'fire_exit_safety'): Promise<{ id: string; status: string }> {
  return request<{ id: string; status: string }>(`/audits/demo?template_id=${encodeURIComponent(templateId)}`, {
    method: 'POST',
  });
}

export async function cancelAudit(id: string): Promise<{ id: string; status: string }> {
  return request<{ id: string; status: string }>(`/audits/${id}/cancel`, {
    method: 'POST',
  });
}

export async function uploadVoiceNote(
  auditId: string,
  audioBlob: Blob,
  timestamp_s: number = 0.0,
): Promise<{ id: string; audit_id: string; timestamp_s: number }> {
  const fd = new FormData();
  fd.append('audio', audioBlob, 'voicenote.wav');
  fd.append('timestamp_s', String(timestamp_s));
  return request<{ id: string; audit_id: string; timestamp_s: number }>(`/audits/${auditId}/voice-notes`, {
    method: 'POST',
    body: fd,
  });
}

export function compareAudits(beforeId: string, afterId: string): Promise<CompareResult> {
  return request<CompareResult>('/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ before_id: beforeId, after_id: afterId }),
  });
}

export function getAuditCost(id: string): Promise<CostSummary> {
  return request<CostSummary>(`/audits/${id}/cost`);
}

export default {
  getHealth,
  getTemplates,
  getTemplate,
  getAudits,
  getAudit,
  createAudit,
  createDemoAudit,
  cancelAudit,
  uploadVoiceNote,
  compareAudits,
  getAuditCost,
};
