import { useState } from 'react';
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  HelpCircle,
  Send,
  Loader2,
  History,
  User,
} from 'lucide-react';
import type { Finding } from '../api/types';
import { reviewFinding, type AuditLogEntry } from '../api/client';
import { getStatusMeta } from '../utils/formatters';

interface ReviewQueuePanelProps {
  auditId: string;
  finding: Finding;
  auditLogs?: AuditLogEntry[];
  onReviewSuccess: (updatedFinding: any, newSummary: any, newLogEntry: AuditLogEntry) => void;
}

export default function ReviewQueuePanel({
  auditId,
  finding,
  auditLogs = [],
  onReviewSuccess,
}: ReviewQueuePanelProps) {
  const [action, setAction] = useState<'approve_ai' | 'override_pass' | 'override_fail'>('approve_ai');
  const [note, setNote] = useState('');
  const [actorLabel, setActorLabel] = useState('Safety Reviewer');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const aiVerdictMeta = getStatusMeta((finding.ai_verdict || finding.status) as any);
  const finalVerdictMeta = getStatusMeta((finding.final_verdict || finding.status) as any);

  const findingLogs = auditLogs.filter((l) => l.finding_id === finding.id);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!note.trim()) {
      setError('A written explanation/justification note is required to submit a review decision.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const res = await reviewFinding(auditId, finding.id, {
        action,
        actor_label: actorLabel.trim() || 'Safety Reviewer',
        note: note.trim(),
      });
      onReviewSuccess(res, res.summary, res.audit_log);
      setNote('');
    } catch (err: any) {
      setError(err?.message || 'Failed to submit review decision');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-5">
      {/* Header & Side-by-Side Verdicts */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-amber-500" />
          <h3 className="font-semibold text-sm text-[var(--color-text)]">
            Human Review Queue · {finding.rule_id}
          </h3>
        </div>

        {/* Side-by-Side AI vs Final Verdict */}
        <div className="flex items-center gap-3 text-xs font-mono">
          <div className="flex items-center gap-1.5">
            <span className="text-[var(--color-text-secondary)]">AI:</span>
            <span className={`px-2 py-0.5 rounded-full font-bold uppercase ${aiVerdictMeta.badgeClass}`}>
              {aiVerdictMeta.label}
            </span>
          </div>
          <span className="text-[var(--color-text-secondary)]">→</span>
          <div className="flex items-center gap-1.5">
            <span className="text-[var(--color-text-secondary)]">Final:</span>
            <span className={`px-2 py-0.5 rounded-full font-bold uppercase ${finalVerdictMeta.badgeClass}`}>
              {finalVerdictMeta.label}
            </span>
          </div>
        </div>
      </div>

      {/* Review Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <label className="block text-xs font-semibold text-[var(--color-text)]">
            Select Review Action:
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <button
              type="button"
              onClick={() => setAction('approve_ai')}
              className={`flex items-center justify-center gap-2 p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                action === 'approve_ai'
                  ? 'border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 ring-2 ring-blue-500/20'
                  : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]'
              }`}
            >
              <HelpCircle className="h-4 w-4" />
              <span>Approve AI Verdict</span>
            </button>

            <button
              type="button"
              onClick={() => setAction('override_pass')}
              className={`flex items-center justify-center gap-2 p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                action === 'override_pass'
                  ? 'border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 ring-2 ring-emerald-500/20'
                  : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]'
              }`}
            >
              <CheckCircle className="h-4 w-4" />
              <span>Override → Pass</span>
            </button>

            <button
              type="button"
              onClick={() => setAction('override_fail')}
              className={`flex items-center justify-center gap-2 p-2.5 rounded-xl border text-xs font-semibold transition-all ${
                action === 'override_fail'
                  ? 'border-rose-500 bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 ring-2 ring-rose-500/20'
                  : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]'
              }`}
            >
              <XCircle className="h-4 w-4" />
              <span>Override → Fail</span>
            </button>
          </div>
        </div>

        {/* Reviewer Actor Label & Justification Note */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-semibold text-[var(--color-text)] mb-1">
              Reviewer Name / Title:
            </label>
            <input
              type="text"
              value={actorLabel}
              onChange={(e) => setActorLabel(e.target.value)}
              placeholder="e.g. Lead Safety Inspector"
              className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-xs text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none"
            />
          </div>

          <div className="sm:col-span-2">
            <label className="block text-xs font-semibold text-[var(--color-text)] mb-1">
              Justification & Finding Note (Required):
            </label>
            <textarea
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Explain visual confirmation, physical inspection details, or override rationale..."
              className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-xs text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none"
            />
          </div>
        </div>

        {error && (
          <p className="text-xs text-rose-600 dark:text-rose-400 font-medium">
            {error}
          </p>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--color-accent)] px-4 py-2 text-xs font-semibold text-white hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer"
          >
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            <span>Commit Review Decision</span>
          </button>
        </div>
      </form>

      {/* Audit Log Chronology for this finding */}
      {findingLogs.length > 0 && (
        <div className="space-y-2 pt-3 border-t border-[var(--color-border)]">
          <h4 className="text-xs font-semibold text-[var(--color-text-secondary)] flex items-center gap-1.5 uppercase tracking-wider">
            <History className="h-3.5 w-3.5" />
            <span>Finding Audit History ({findingLogs.length})</span>
          </h4>
          <div className="space-y-2">
            {findingLogs.map((log) => (
              <div
                key={log.id}
                className="p-3 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-xs space-y-1 font-mono"
              >
                <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                  <span className="flex items-center gap-1 text-[var(--color-text)] font-semibold">
                    <User className="h-3 w-3" />
                    {log.actor_label} ({log.action})
                  </span>
                  <span>{new Date(log.ts).toLocaleString()}</span>
                </div>
                <div className="text-[var(--color-text)] font-sans">
                  "{log.note}"
                </div>
                <div className="text-[10px] text-[var(--color-text-secondary)]">
                  Verdict Transition: <span className="uppercase font-bold">{log.before}</span> → <span className="uppercase font-bold text-[var(--color-text)]">{log.after}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
