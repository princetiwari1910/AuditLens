import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  Layers,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  HelpCircle,
  Loader2,
} from 'lucide-react';
import { getAudits, compareAudits, getAudit, type CompareResult } from '../api/client';
import type { Audit } from '../api/types';
import Disclaimer from '../components/Disclaimer';

export default function Compare() {
  const [searchParams] = useSearchParams();
  const beforeParam = searchParams.get('before') || '';
  const afterParam = searchParams.get('after') || '';

  const [audits, setAudits] = useState<Audit[]>([]);
  const [beforeId, setBeforeId] = useState(beforeParam);
  const [afterId, setAfterId] = useState(afterParam);

  const [beforeAudit, setBeforeAudit] = useState<Audit | null>(null);
  const [afterAudit, setAfterAudit] = useState<Audit | null>(null);
  const [comparison, setComparison] = useState<CompareResult | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load audit list
  useEffect(() => {
    getAudits().then((list) => {
      setAudits(list);
      // Auto-select first two if not in params
      if (!beforeId && list.length >= 2) {
        setBeforeId(list[1].id);
        setAfterId(list[0].id);
      }
    });
  }, []);

  // Run comparison when IDs change
  useEffect(() => {
    if (!beforeId || !afterId || beforeId === afterId) return;

    setIsLoading(true);
    setError(null);

    Promise.all([
      getAudit(beforeId).then(setBeforeAudit),
      getAudit(afterId).then(setAfterAudit),
      compareAudits(beforeId, afterId).then(setComparison),
    ])
      .catch((err) => {
        setError(err.message || 'Comparison failed.');
      })
      .finally(() => setIsLoading(false));
  }, [beforeId, afterId]);

  const scoreBefore = beforeAudit?.summary?.score ?? 0;
  const scoreAfter = afterAudit?.summary?.score ?? 0;
  const scoreDiff = scoreAfter - scoreBefore;

  function renderStatusBadge(status: string) {
    switch (status) {
      case 'resolved':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-800 dark:bg-green-950 dark:text-green-200">
            <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
            Resolved
          </span>
        );
      case 'new_issue':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-800 dark:bg-red-950 dark:text-red-200">
            <XCircle className="h-3.5 w-3.5 text-red-600" />
            New Issue
          </span>
        );
      case 'still_open':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-800 dark:bg-rose-950 dark:text-rose-200">
            <AlertCircle className="h-3.5 w-3.5 text-rose-600" />
            Still Open
          </span>
        );
      case 'unchanged_pass':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
            <CheckCircle2 className="h-3.5 w-3.5 text-slate-500" />
            Unchanged Pass
          </span>
        );
      case 'unsure_change':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-950 dark:text-amber-200">
            <HelpCircle className="h-3.5 w-3.5 text-amber-600" />
            Review Needed
          </span>
        );
    }
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      {/* Navbar */}
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 sm:px-6 py-3.5 sticky top-0 z-20">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-2">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors shrink-0 min-h-[36px]"
          >
            <ArrowLeft className="h-4 w-4" />
            Home
          </Link>
          <span className="text-xs font-mono text-[var(--color-text-secondary)] truncate">
            <span className="hidden sm:inline">AuditLens Differential Re-Audit Verification</span>
            <span className="sm:hidden">Differential Comparison</span>
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
        {/* Title */}
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50/70 px-3 py-0.5 text-xs font-medium text-blue-800 dark:border-blue-900 dark:bg-blue-950/50 dark:text-blue-200">
            <Layers className="h-3.5 w-3.5" />
            Remediation Proof Engine
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-[var(--color-text)]">
            Before vs. After Walkthrough Comparison
          </h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Compare initial walkthrough findings against a subsequent re-inspection to verify remediation.
          </p>
        </div>

        {/* Audit Selectors Card */}
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-sm">
          <div className="grid sm:grid-cols-2 gap-6">
            {/* Before Selector */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)] block">
                1. Baseline Walkthrough (Before)
              </label>
              <select
                value={beforeId}
                onChange={(e) => setBeforeId(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-xs font-mono text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              >
                <option value="">Select Baseline Audit</option>
                {audits.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.template_id || 'General'} ({a.id ? a.id.slice(0, 8) : ''}) · Score: {a.summary?.score ?? 0}
                  </option>
                ))}
              </select>
            </div>

            {/* After Selector */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)] block">
                2. Re-Audit Walkthrough (After Remediation)
              </label>
              <select
                value={afterId}
                onChange={(e) => setAfterId(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-xs font-mono text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              >
                <option value="">Select Re-Audit</option>
                {audits.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.template_id || 'General'} ({a.id ? a.id.slice(0, 8) : ''}) · Score: {a.summary?.score ?? 0}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center p-12">
            <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent)]" />
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-900">
            {error}
          </div>
        )}

        {/* Comparison Summary Banner */}
        {comparison && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="rounded-xl border border-green-200 bg-green-50/70 p-4 dark:border-green-900/60 dark:bg-green-950/30">
                <span className="text-[11px] font-semibold text-green-800 dark:text-green-300 uppercase">
                  Resolved Issues
                </span>
                <span className="font-mono text-2xl font-black text-green-700 dark:text-green-200 block mt-1">
                  {comparison.summary.resolved}
                </span>
              </div>

              <div className="rounded-xl border border-red-200 bg-red-50/70 p-4 dark:border-red-900/60 dark:bg-red-950/30">
                <span className="text-[11px] font-semibold text-red-800 dark:text-red-300 uppercase">
                  New Issues Found
                </span>
                <span className="font-mono text-2xl font-black text-red-700 dark:text-red-200 block mt-1">
                  {comparison.summary.new_issue}
                </span>
              </div>

              <div className="rounded-xl border border-rose-200 bg-rose-50/70 p-4 dark:border-rose-900/60 dark:bg-rose-950/30">
                <span className="text-[11px] font-semibold text-rose-800 dark:text-rose-300 uppercase">
                  Still Open
                </span>
                <span className="font-mono text-2xl font-black text-rose-700 dark:text-rose-200 block mt-1">
                  {comparison.summary.still_open}
                </span>
              </div>

              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                <span className="text-[11px] font-semibold text-[var(--color-text-secondary)] uppercase">
                  Compliance Score Delta
                </span>
                <span className={`font-mono text-2xl font-black block mt-1 flex items-center gap-1 ${
                  scoreDiff > 0 ? 'text-green-600' : scoreDiff < 0 ? 'text-red-600' : 'text-slate-600'
                }`}>
                  {scoreDiff > 0 ? <TrendingUp className="h-5 w-5" /> : scoreDiff < 0 ? <TrendingDown className="h-5 w-5" /> : <Minus className="h-5 w-5" />}
                  {scoreDiff > 0 ? `+${scoreDiff}` : scoreDiff}
                  <span className="text-xs font-normal text-[var(--color-text-secondary)]">pts</span>
                </span>
              </div>
            </div>

            {/* Per-Rule Comparison Table */}
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-sm">
              <div className="border-b border-[var(--color-border)] px-6 py-4">
                <h3 className="font-semibold text-sm text-[var(--color-text)]">
                  Per-Rule Progression
                </h3>
              </div>

              <div className="divide-y divide-[var(--color-border)]">
                {comparison.results.map((item) => (
                  <div key={item.rule_id} className="p-5 space-y-2 hover:bg-[var(--color-bg-secondary)] transition-colors">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <span className="font-semibold text-sm text-[var(--color-text)]">
                          {item.rule_title || item.rule_id}
                        </span>
                        <span className="block font-mono text-xs text-[var(--color-text-secondary)]">
                          {item.rule_id}
                        </span>
                      </div>

                      <div className="flex items-center gap-4">
                        {/* Before / After status chips */}
                        <div className="flex items-center gap-2 text-xs font-mono">
                          <span className="text-[var(--color-text-secondary)] uppercase">
                            {item.before_status || 'N/A'}
                          </span>
                          <ArrowRight className="h-3 w-3 text-slate-400" />
                          <span className="font-bold text-[var(--color-text)] uppercase">
                            {item.after_status || 'N/A'}
                          </span>
                        </div>

                        {renderStatusBadge(item.status)}
                      </div>
                    </div>

                    {item.rationale && (
                      <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                        {item.rationale}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <Disclaimer />
      </main>
    </div>
  );
}
