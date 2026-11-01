import { useState, useEffect } from 'react';
import {
  Wrench,
  Clock,
  Calendar,
  CheckSquare,
  Sparkles,
} from 'lucide-react';
import { getFixPlan, type FixAction } from '../api/client';
import { getSeverityMeta } from '../utils/formatters';

interface FixPlanSectionProps {
  auditId: string;
  onSelectFinding?: (findingId: string) => void;
}

export default function FixPlanSection({
  auditId,
  onSelectFinding,
}: FixPlanSectionProps) {
  const [actions, setActions] = useState<FixAction[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    getFixPlan(auditId)
      .then((data) => {
        if (isMounted) {
          setActions(data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        console.error('Failed to load fix plan:', err);
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [auditId]);

  if (isLoading) {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
          <Wrench className="h-4 w-4 animate-spin text-[var(--color-accent)]" />
          <span>Generating prioritized corrective action plan...</span>
        </div>
      </section>
    );
  }

  if (actions.length === 0) {
    return null;
  }

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 space-y-4 shadow-sm print:border-slate-300 print:shadow-none print:break-inside-avoid">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[var(--color-border)] pb-3">
        <div className="flex items-center gap-2">
          <Wrench className="h-5 w-5 text-indigo-500" />
          <div>
            <h3 className="font-bold text-sm text-[var(--color-text)] flex items-center gap-2">
              <span>Prioritized Corrective Action Plan</span>
              <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-mono font-bold text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 flex items-center gap-1">
                <Sparkles className="h-3 w-3" />
                AI-Suggested (MOCK)
              </span>
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)]">
              Sequenced remediation recommendations prioritized by severity and egress impact.
            </p>
          </div>
        </div>
        <div className="text-xs font-mono text-[var(--color-text-secondary)] flex items-center gap-2">
          <CheckSquare className="h-3.5 w-3.5 text-emerald-500" />
          <span>{actions.length} action items</span>
        </div>
      </div>

      {/* Action Items List */}
      <div className="space-y-3">
        {actions.map((act, idx) => {
          const sevMeta = getSeverityMeta(act.severity as any);
          const effortColor =
            act.effort === 'S'
              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800'
              : act.effort === 'M'
              ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 border-amber-300 dark:border-amber-800'
              : 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300 border-rose-300 dark:border-rose-800';

          return (
            <div
              key={`${act.finding_id}_${idx}`}
              className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] space-y-2 hover:border-slate-300 transition-colors"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 dark:bg-slate-800 font-mono text-[11px] font-bold text-[var(--color-text)]">
                    {idx + 1}
                  </span>
                  <span className="font-semibold text-xs text-[var(--color-text)]">
                    {act.rule_id}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-[11px] font-mono">
                  <span className={`px-2 py-0.5 rounded font-medium ${sevMeta.badge}`}>
                    {sevMeta.label}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded font-bold border uppercase tracking-wider ${effortColor}`}
                  >
                    Effort {act.effort}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[var(--color-text-secondary)] rounded bg-[var(--color-surface)] border border-[var(--color-border)] px-2 py-0.5">
                    <Calendar className="h-3 w-3 text-indigo-500" />
                    Due in {act.suggested_due_days}d
                  </span>
                </div>
              </div>

              <p className="text-xs text-[var(--color-text)] leading-relaxed">
                {act.suggested_fix}
              </p>

              {onSelectFinding && (
                <div className="pt-1 flex justify-end print:hidden">
                  <button
                    type="button"
                    onClick={() => onSelectFinding(act.finding_id)}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--color-accent)] hover:underline cursor-pointer"
                  >
                    <Clock className="h-3 w-3" />
                    <span>View Finding Footage & Evidence</span>
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
