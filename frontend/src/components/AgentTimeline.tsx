import React from 'react';
import {
  CheckCircle2,
  Clock,
  AlertCircle,
  Wrench,
  Search,
  Ruler,
  Layers,
  Sparkles,
  ShieldAlert,
} from 'lucide-react';
import type { SSEEvent } from '../api/types';
import { getStatusMeta } from '../utils/formatters';

interface AgentTimelineProps {
  events: SSEEvent[];
  currentRule?: string;
  currentTool?: string;
  progressPercent: number;
  isCompleted?: boolean;
  error?: string | null;
}

export default function AgentTimeline({
  events,
  currentRule,
  currentTool,
  progressPercent,
  isCompleted,
  error,
}: AgentTimelineProps) {
  function getToolIcon(toolName: string) {
    switch (toolName) {
      case 'find_objects':
        return <Search className="h-4 w-4 text-blue-500" />;
      case 'measure_clear_width':
        return <Ruler className="h-4 w-4 text-emerald-500" />;
      case 'check_colocation':
        return <Layers className="h-4 w-4 text-amber-500" />;
      default:
        return <Wrench className="h-4 w-4 text-slate-500" />;
    }
  }

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-sm">
      {/* Header & Progress Bar */}
      <div className="mb-6 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-[var(--color-text)] flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-[var(--color-accent)] animate-pulse" />
              Autonomous Agent Execution
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
              Evidence-First planning over registered visual & geometric tools
            </p>
          </div>
          <span className="font-mono text-xs font-semibold text-[var(--color-accent)]">
            {progressPercent}%
          </span>
        </div>

        {/* Animated Progress Bar */}
        <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg-secondary)]">
          <div
            className="h-full bg-[var(--color-accent)] transition-all duration-300 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        {currentRule && !isCompleted && !error && (
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] pt-1">
            <span className="inline-block h-2 w-2 rounded-full bg-blue-500 animate-ping" />
            <span>Evaluating rule:</span>
            <span className="font-mono font-medium text-[var(--color-text)]">{currentRule}</span>
          </div>
        )}
      </div>

      {/* Events Stream List */}
      <div className="space-y-3 max-h-[460px] overflow-y-auto pr-2 scrollbar-thin">
        {events.map((evt, idx) => {
          const p = evt.payload;

          if (evt.type === 'audit_started') {
            return (
              <div key={idx} className="flex items-start gap-3 rounded-lg bg-[var(--color-bg-secondary)] p-3 text-xs">
                <CheckCircle2 className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
                <div>
                  <span className="font-medium text-[var(--color-text)]">Audit initiated</span>
                  <p className="text-[var(--color-text-secondary)]">
                    Loaded {String(p.rule_count || 0)} checklist rules across {String(p.frame_count || 0)} sampled walkthrough frames
                  </p>
                </div>
              </div>
            );
          }

          if (evt.type === 'tool_call') {
            const tool = String(p.tool || 'tool');
            return (
              <div key={idx} className="flex items-start gap-3 rounded-lg border border-[var(--color-border)] p-3 text-xs">
                {getToolIcon(tool)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-medium text-[var(--color-text)]">
                      call: {tool}()
                    </span>
                    <span className="text-[10px] text-[var(--color-text-secondary)] font-mono">
                      {p.rule_id ? String(p.rule_id) : ''}
                    </span>
                  </div>
                  {p.args_summary && (
                    <p className="text-[var(--color-text-secondary)] font-mono text-[11px] truncate mt-0.5">
                      args: {JSON.stringify(p.args_summary)}
                    </p>
                  )}
                </div>
              </div>
            );
          }

          if (evt.type === 'tool_result') {
            return (
              <div key={idx} className="ml-6 flex items-center justify-between rounded-md bg-[var(--color-bg-secondary)] px-3 py-1.5 text-xs">
                <span className="text-[var(--color-text-secondary)]">
                  ↪ {String(p.result_summary || 'Done')}
                </span>
                {p.duration_ms !== undefined && (
                  <span className="text-[10px] font-mono text-[var(--color-text-secondary)]">
                    {String(p.duration_ms)}ms
                  </span>
                )}
              </div>
            );
          }

          if (evt.type === 'finding_recorded') {
            const status = String(p.status || 'unsure');
            const meta = getStatusMeta(status);
            return (
              <div key={idx} className={`flex items-start justify-between rounded-lg border p-3 text-xs ${meta.badgeClass}`}>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{meta.label}</span>
                    <span className="font-mono">{String(p.rule_id || '')}</span>
                  </div>
                  <p className="text-[11px] opacity-90 leading-tight">
                    {String(p.rationale || '')}
                  </p>
                </div>
                {p.confidence !== undefined && (
                  <span className="font-mono font-semibold ml-2 shrink-0">
                    {Math.round(Number(p.confidence) * 100)}%
                  </span>
                )}
              </div>
            );
          }

          if (evt.type === 'audit_completed') {
            return (
              <div key={idx} className="flex items-center gap-3 rounded-lg bg-green-50 p-3 text-xs text-green-900 border border-green-200 dark:bg-green-950/60 dark:text-green-200 dark:border-green-800">
                <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
                <div>
                  <span className="font-semibold">Audit Completed Successfully</span>
                  <p className="text-[11px] opacity-90">
                    All checklist rules evaluated. Generating final evidence report...
                  </p>
                </div>
              </div>
            );
          }

          if (evt.type === 'error') {
            return (
              <div key={idx} className="flex items-center gap-3 rounded-lg bg-red-50 p-3 text-xs text-red-900 border border-red-200 dark:bg-red-950/60 dark:text-red-200 dark:border-red-800">
                <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
                <div>
                  <span className="font-semibold">Execution Error</span>
                  <p className="text-[11px] opacity-90">{String(p.error || 'Failed')}</p>
                </div>
              </div>
            );
          }

          return null;
        })}
      </div>
    </div>
  );
}
