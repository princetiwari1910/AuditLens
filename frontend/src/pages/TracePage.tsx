import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Activity,
  Zap,
  DollarSign,
  Clock,
  Layers,
  AlertCircle,
  Database,
  Cpu,
} from 'lucide-react';
import { getAuditTrace, type AuditTraceResponse } from '../api/client';

export interface TracePageProps {
  initialTrace?: AuditTraceResponse | null;
}

export default function TracePage({ initialTrace = null }: TracePageProps = {}) {
  const { id } = useParams<{ id: string }>();
  const [trace, setTrace] = useState<AuditTraceResponse | null>(initialTrace);
  const [isLoading, setIsLoading] = useState(!initialTrace);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialTrace) return;
    if (!id) return;
    setIsLoading(true);
    setError(null);
    getAuditTrace(id)
      .then((data) => {
        setTrace(data);
        setIsLoading(false);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to load execution trace.');
        setIsLoading(false);
      });
  }, [id]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)]">
        <div className="flex flex-col items-center gap-2">
          <Activity className="h-6 w-6 animate-pulse text-[var(--color-accent)]" />
          <p className="text-xs text-[var(--color-text-secondary)]">Loading execution trace...</p>
        </div>
      </div>
    );
  }

  if (error || !trace) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-bg)] px-6">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-center max-w-sm">
          <AlertCircle className="mx-auto h-8 w-8 text-rose-500 mb-2" />
          <h2 className="text-sm font-bold text-[var(--color-text)]">Trace Unavailable</h2>
          <p className="text-xs text-[var(--color-text-secondary)] mt-1">{error || 'Trace not found'}</p>
          <Link
            to={id ? `/audits/${id}` : '/'}
            className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-3 py-1.5 text-xs text-white"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to Report
          </Link>
        </div>
      </div>
    );
  }

  const { totals, spans } = trace;
  const budgetLimitUsd = 0.05;
  const budgetPercent = Math.min(100, Math.round((totals.total_cost_usd / budgetLimitUsd) * 100));

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      {/* Top Navbar */}
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4 sticky top-0 z-20">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <Link
            to={`/audits/${id}`}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Inspection Report
          </Link>

          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-emerald-500" />
            <span className="text-xs font-semibold text-[var(--color-text)]">
              Execution Observability Trace
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
        {/* Title */}
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text)]">
            Audit Execution Trace & Budget Accounting
          </h1>
          <p className="text-xs text-[var(--color-text-secondary)] font-mono mt-0.5">
            Audit ID: {trace.audit_id} · {spans.length} instrumented spans
          </p>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-1">
            <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
              <Clock className="h-3.5 w-3.5 text-blue-500" />
              Total Latency
            </span>
            <div className="text-xl font-bold text-[var(--color-text)] font-mono">
              {totals.total_latency_ms} ms
            </div>
            <p className="text-[10px] text-[var(--color-text-secondary)]">
              Parallel execution
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-1">
            <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
              <DollarSign className="h-3.5 w-3.5 text-green-500" />
              Cost / Budget
            </span>
            <div className="text-xl font-bold text-green-700 dark:text-green-400 font-mono">
              ${totals.total_cost_usd.toFixed(4)}
            </div>
            <div className="w-full bg-slate-200 dark:bg-slate-700 h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-emerald-500 h-full rounded-full"
                style={{ width: `${budgetPercent}%` }}
              />
            </div>
            <p className="text-[10px] text-[var(--color-text-secondary)] font-mono">
              {budgetPercent}% of ${budgetLimitUsd} guard
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-1">
            <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
              <Database className="h-3.5 w-3.5 text-amber-500" />
              Cache Hits
            </span>
            <div className="text-xl font-bold text-[var(--color-text)] font-mono">
              {totals.cache_hits} ({Math.round(totals.cache_hit_rate * 100)}%)
            </div>
            <p className="text-[10px] text-[var(--color-text-secondary)]">
              {totals.calls_saved_by_cache} network calls saved
            </p>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-1">
            <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
              <Layers className="h-3.5 w-3.5 text-indigo-500" />
              Keyframes
            </span>
            <div className="text-xl font-bold text-[var(--color-text)] font-mono">
              {totals.frames_considered
                ? `${totals.frames_analyzed} of ${totals.frames_considered}`
                : `${totals.frames_analyzed} frames`}
            </div>
            <p className="text-[10px] text-[var(--color-text-secondary)] font-mono">
              {totals.frames_considered
                ? `${totals.frames_analyzed} of ${totals.frames_considered} frames analyzed`
                : `${totals.frames_analyzed} frames analyzed`}
            </p>
          </div>
        </div>

        {/* Span Waterfall Timeline */}
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 space-y-4 shadow-sm">
          <h3 className="font-bold text-sm text-[var(--color-text)] flex items-center gap-2">
            <Activity className="h-4 w-4 text-[var(--color-accent)]" />
            <span>Execution Timeline Spans</span>
          </h3>

          <div className="space-y-2.5">
            {spans.map((span, idx) => {
              const stageColors: Record<string, string> = {
                keyframe_selection: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300',
                segmentation: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
                escalation_tile: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
                escalation_neighbor: 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300',
                escalation_spark: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300',
                reasoning: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
              };
              const colorClass = stageColors[span.stage] || 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300';

              return (
                <div
                  key={span.id || idx}
                  className="p-3 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-xs space-y-1.5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-[var(--color-text-secondary)]">
                        #{idx + 1}
                      </span>
                      <span className={`px-2 py-0.5 rounded font-mono font-bold uppercase text-[10px] ${colorClass}`}>
                        {span.stage.replace('_', ' ')}
                      </span>
                      <span className="font-semibold text-[var(--color-text)] flex items-center gap-1 font-mono">
                        <Cpu className="h-3 w-3 text-slate-400" />
                        {span.model}
                      </span>
                      {span.concept && (
                        <span className="text-[11px] text-[var(--color-text-secondary)] italic">
                          "{span.concept}"
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-3 font-mono text-[11px]">
                      {span.cache_hit ? (
                        <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 font-bold">
                          <Zap className="h-3 w-3" />
                          CACHE HIT
                        </span>
                      ) : (
                        <span className="text-slate-400">MISS</span>
                      )}
                      <span className="text-[var(--color-text)] font-semibold">
                        {span.latency_ms} ms
                      </span>
                      <span className="text-green-700 dark:text-green-400">
                        ${span.cost_usd.toFixed(4)}
                      </span>
                    </div>
                  </div>

                  {span.step_reason && (
                    <p className="text-[11px] text-[var(--color-text-secondary)] pl-6">
                      {span.step_reason}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </main>
    </div>
  );
}
