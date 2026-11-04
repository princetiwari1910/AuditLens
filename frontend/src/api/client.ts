/** Typed API client for AuditLens backend. */

import type { Audit, Template } from './types';
import { buildApiUrl } from './config';
import { DEFAULT_TEMPLATES } from '../data/defaultTemplates';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const targetUrl = buildApiUrl(path);
  const res = await fetch(targetUrl, {
    ...init,
  });

  const contentType = (res.headers && typeof res.headers.get === 'function')
    ? res.headers.get('content-type') || ''
    : '';

  let rawText = '';
  let textRead = false;
  if (typeof res.text === 'function') {
    try {
      rawText = await res.text();
      textRead = true;
    } catch {
      // In case body was already handled
    }
  }

  if (!res.ok) {
    let errMsg = `API error ${res.status}`;
    if (textRead && rawText) {
      try {
        const errJson = JSON.parse(rawText);
        if (typeof errJson === 'object' && errJson !== null) {
          errMsg = errJson.detail || errJson.message || errMsg;
        }
      } catch {
        errMsg = rawText;
      }
    } else if (!textRead && typeof res.json === 'function') {
      try {
        const errJson = await res.json();
        if (typeof errJson === 'object' && errJson !== null) {
          errMsg = errJson.detail || errJson.message || errMsg;
        }
      } catch {
        // ignore
      }
    }
    throw new ApiError(errMsg, res.status);
  }

  const trimmed = rawText ? rawText.trim() : '';

  // Detect HTML responses (SPA fallback / 404 / 502 error pages returned with 200 OK)
  const isHtml =
    contentType.includes('text/html') ||
    trimmed.startsWith('<!DOCTYPE') ||
    trimmed.startsWith('<!doctype') ||
    trimmed.startsWith('<html');

  if (isHtml) {
    throw new ApiError(
      `Expected JSON from ${path}, but received HTML. The backend service may be initializing or VITE_API_BASE_URL is not set.`,
      502
    );
  }

  if (textRead) {
    if (!trimmed) {
      return {} as T;
    }
    try {
      return JSON.parse(trimmed) as T;
    } catch (e) {
      throw new ApiError(
        `Failed to parse JSON response from ${path}: ${(e as Error).message}`,
        500
      );
    }
  }

  if (typeof res.json === 'function') {
    try {
      return (await res.json()) as T;
    } catch (e) {
      throw new ApiError(
        `Failed to parse JSON from ${path}: ${(e as Error).message}`,
        500
      );
    }
  }

  return {} as T;
}

export interface HealthResponse {
  status: string;
  provider_mode: string;
  data_dir?: string;
  demo_replay?: boolean;
  models?: {
    segmentation?: string;
    agent?: string;
    transcription?: string;
  };
}

export interface ProviderCostData {
  name?: string;
  model_id?: string;
  role?: string;
  calls: number;
  cache_hits?: number;
  latency_ms?: number;
  units: number;
  cost_usd: number;
  simulated?: boolean;
}

export interface CostSummary {
  audit_id: string;
  provider_mode?: string;
  total_calls: number;
  total_cost_usd: number;
  by_provider: Record<string, ProviderCostData>;
  models?: {
    segmentation?: string;
    agent?: string;
    transcription?: string;
  };
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

export async function getTemplates(): Promise<Template[]> {
  try {
    const data = await request<Template[]>('/templates');
    if (Array.isArray(data) && data.length > 0) {
      return data;
    }
  } catch (err) {
    console.warn('Backend templates unreachable, using bundled fallback templates:', err);
  }
  return DEFAULT_TEMPLATES;
}

export interface CompileTemplateResponse {
  template: Template;
  valid: boolean;
  errors: string[];
  warnings?: string[];
}

export function compileTemplate(text: string): Promise<CompileTemplateResponse> {
  return request<CompileTemplateResponse>('/templates/compile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
}

export async function getTemplate(id: string): Promise<Template> {
  try {
    const data = await request<Template>(`/templates/${id}`);
    if (data && typeof data === 'object' && data.id) {
      return data;
    }
  } catch (err) {
    console.warn(`Template '${id}' fetch failed, checking fallback templates:`, err);
  }
  const fallback = DEFAULT_TEMPLATES.find((t) => t.id === id);
  if (fallback) return fallback;
  return DEFAULT_TEMPLATES[0];
}

export async function getAudits(): Promise<Audit[]> {
  try {
    const data = await request<Audit[]>('/audits');
    if (Array.isArray(data)) {
      return data;
    }
    return [];
  } catch (err) {
    console.warn('Failed to fetch audits from backend:', err);
    return [];
  }
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

export async function createDemoAudit(
  templateId: string = 'campus_fire_exit_core',
  replay: boolean = false,
): Promise<{ id: string; status: string }> {
  const query = new URLSearchParams();
  if (templateId) query.set('template_id', templateId);
  if (replay) query.set('replay', 'true');
  return request<{ id: string; status: string }>(`/audits/demo?${query.toString()}`, {
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

export interface EvalLatestResponse {
  timestamp: string;
  provider_mode: string;
  allow_mock: boolean;
  simulated: boolean;
  benchmark_details: any[];
  pipeline_summary: {
    mode: string;
    total_clips: number;
    total_evaluations: number;
    correct_count: number;
    unsure_count: number;
    overall_accuracy: number;
    unsure_rate: number;
    macro_precision: number;
    macro_recall: number;
    macro_f1: number;
    average_latency_s: number;
    average_cost_usd: number;
    rule_metrics: Record<string, any>;
    reliability_curve: Array<{ bin: string; count: number; confidence: number; accuracy: number }>;
    accuracy_vs_abstain: Array<{ threshold: number; abstain_rate: number; accuracy: number; decided_count: number }>;
    failure_cases: Array<{
      clip_file: string;
      rule_id: string;
      ground_truth: string;
      prediction: string;
      confidence: number;
      frame_idx: number;
      timestamp_s: number;
      frame_link: string;
      rationale: string;
    }>;
  };
  baseline_summary?: any;
}

export function getLatestEval(): Promise<EvalLatestResponse> {
  return request<EvalLatestResponse>('/eval/latest');
}

export interface AuditLogEntry {
  id: string;
  audit_id: string;
  finding_id: string;
  actor_label: string;
  action: string;
  before: string;
  after: string;
  note: string;
  ts: string;
}

export interface ReviewFindingResponse {
  finding_id: string;
  ai_verdict: string;
  final_verdict: string;
  status: string;
  audit_log: AuditLogEntry;
  summary: any;
}

export function reviewFinding(
  auditId: string,
  findingId: string,
  payload: { action: string; actor_label?: string; note: string }
): Promise<ReviewFindingResponse> {
  return request<ReviewFindingResponse>(`/audits/${auditId}/findings/${findingId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getAuditLog(auditId: string): Promise<AuditLogEntry[]> {
  return request<AuditLogEntry[]>(`/audits/${auditId}/audit_log`);
}

export interface FixAction {
  finding_id: string;
  rule_id: string;
  severity: 'high' | 'medium' | 'low';
  effort: 'S' | 'M' | 'L';
  suggested_fix: string;
  suggested_due_days: number;
  label: string;
}

export function getFixPlan(auditId: string): Promise<FixAction[]> {
  return request<FixAction[]>(`/audits/${auditId}/fix_plan`);
}

export interface Site {
  id: string;
  name: string;
  location_label: string;
  created_at?: string;
  audit_count: number;
  latest_score?: number | null;
  latest_audit_id?: string | null;
}

export interface ScoreTrendItem {
  audit_id: string;
  created_at: string;
  score: number;
  pass_count: number;
  fail_count: number;
  unsure_count: number;
}

export interface SiteTrends {
  site: {
    id: string;
    name: string;
    location_label: string;
    created_at?: string;
  };
  score_trend: ScoreTrendItem[];
  open_issues: Array<{
    finding_id: string;
    rule_id: string;
    status?: string;
    severity: string;
    rationale: string;
    fix_text: string;
  }>;
  recurring_issues: Array<{
    rule_id: string;
    fail_occurrences: number;
  }>;
  resolved_issues: Array<{
    rule_id: string;
    status: string;
    note: string;
  }>;
  trend_notice?: string | null;
}

export function getSites(): Promise<Site[]> {
  return request<Site[]>('/sites');
}

export function getSiteAudits(siteId: string): Promise<Audit[]> {
  return request<Audit[]>(`/sites/${siteId}/audits`);
}

export function getSiteTrends(siteId: string): Promise<SiteTrends> {
  return request<SiteTrends>(`/sites/${siteId}/trends`);
}

export interface ShareResponse {
  token: string;
  share_url: string;
  created_at: string;
}

export function createShareLink(auditId: string): Promise<ShareResponse> {
  return request<ShareResponse>(`/audits/${auditId}/share`, {
    method: 'POST',
  });
}

export function getSharedAudit(token: string): Promise<Audit> {
  return request<Audit>(`/share/${token}`);
}

export interface TraceSpan {
  id: number;
  audit_id: string;
  stage: string;
  model: string;
  concept: string | null;
  latency_ms: number;
  cost_usd: number;
  cache_hit: boolean;
  retries: number;
  step_reason: string;
  simulated?: boolean;
}

export interface AuditTraceResponse {
  audit_id: string;
  spans: TraceSpan[];
  totals: {
    total_spans: number;
    total_latency_ms: number;
    total_cost_usd: number;
    budget_cap_usd?: number;
    cache_hits: number;
    cache_hit_rate: number;
    frames_considered: number;
    frames_analyzed: number;
    calls_saved_by_cache: number;
    frames_saved_by_selection: number;
  };
}

export function getAuditTrace(auditId: string): Promise<AuditTraceResponse> {
  return request<AuditTraceResponse>(`/audits/${auditId}/trace`);
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
  getLatestEval,
  reviewFinding,
  getAuditLog,
};
