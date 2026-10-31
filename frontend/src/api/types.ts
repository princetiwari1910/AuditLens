/** Shared TypeScript types matching the backend Pydantic models. */

export type AuditStatus = 'queued' | 'processing' | 'completed' | 'failed';
export type FindingStatus = 'pass' | 'fail' | 'unsure';
export type RuleType = 'presence' | 'absence' | 'count' | 'measurement' | 'colocation';

export interface Template {
  id: string;
  name: string;
  description: string;
  rules: Rule[];
  disclaimer: string;
}

export interface Rule {
  id: string;
  title: string;
  type: RuleType;
  severity: 'high' | 'medium' | 'low';
  sam_prompts: string[];
  params: Record<string, unknown>;
  fix_text: string;
  detector?: string;
  evidence_needed?: string;
}

export interface Finding {
  id: string;
  rule_id: string;
  status: FindingStatus;
  confidence: number;
  timestamp_s: number;
  frame_idx: number;
  overlay_url: string;
  rationale: string;
  fix_text: string;
  severity: string;
  measurement?: Record<string, unknown>;
  sources: string[];
}

export interface AuditSummary {
  pass: number;
  fail: number;
  unsure: number;
  score: number;
  frames_analyzed?: number;
  frames_considered?: number;
}

export interface Audit {
  id: string;
  status: AuditStatus;
  template_id: string;
  created_at: string;
  duration_s?: number;
  video_url?: string | null;
  summary?: AuditSummary;
  findings: Finding[];
  error?: string;
  provider_mode?: string;
  model_segmentation?: string;
  model_agent?: string;
  model_transcription?: string;
  is_replay?: boolean;
  models?: {
    segmentation?: string;
    agent?: string;
    transcription?: string;
  };
}

export interface SSEEvent {
  type:
    | 'audit_started'
    | 'frames_sampled'
    | 'tool_call'
    | 'tool_result'
    | 'finding_recorded'
    | 'audit_completed'
    | 'error';
  ts: string;
  audit_id: string;
  payload: Record<string, unknown>;
}
