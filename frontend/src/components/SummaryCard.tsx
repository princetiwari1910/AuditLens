import type { AuditSummary } from '../api/types';
import { getScoreGrade } from '../utils/formatters';
import { Calendar, FileText, CheckCircle2, XCircle, HelpCircle } from 'lucide-react';

interface SummaryCardProps {
  summary: AuditSummary | undefined;
  templateId: string;
  auditId: string;
  createdAt: string;
  isReplay?: boolean;
  providerMode?: string;
  sourceProviderMode?: string;
}

export default function SummaryCard({
  summary,
  templateId,
  auditId,
  createdAt,
  isReplay = false,
  providerMode,
  sourceProviderMode,
}: SummaryCardProps) {
  const score = summary?.score ?? 0;
  const grade = getScoreGrade(score);

  // SVG circular ring calculation (r = 44 -> circumference = 2 * PI * 44 = ~276.46)
  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-sm print:border-slate-300 print:shadow-none">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        {/* Left: Audit Meta Details */}
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-2 rounded-md bg-blue-50 px-2.5 py-1 text-xs font-mono font-medium text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 print:border print:border-slate-300">
              <FileText className="h-3.5 w-3.5" />
              <span>{templateId.replace(/_/g, ' ').toUpperCase()}</span>
            </div>
            {isReplay && (
              <span className="rounded-md bg-amber-500/20 px-2.5 py-1 text-xs font-mono font-bold text-amber-700 dark:text-amber-400 border border-amber-500/30">
                {sourceProviderMode === 'record' ? 'RECORDED RUN (live providers)' : 'SIMULATED REPLAY (mock fixtures)'}
              </span>
            )}
            {providerMode && (
              <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-1 text-[11px] font-mono text-slate-600 dark:text-slate-300 uppercase">
                {providerMode}
              </span>
            )}
            {summary && (summary.frames_analyzed !== undefined || summary.frames_considered !== undefined) && (
              <span className="inline-flex items-center rounded-md bg-slate-100 dark:bg-slate-800 px-2.5 py-1 text-xs font-mono font-medium text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                {summary.frames_considered
                  ? `${summary.frames_analyzed ?? 0} of ${summary.frames_considered} frames analyzed`
                  : `${summary.frames_analyzed ?? 0} frames analyzed`}
              </span>
            )}
          </div>

          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--color-text)]">
            Pre-Audit Inspection Report
          </h2>

          <div className="flex flex-wrap items-center gap-y-1 gap-x-4 text-xs font-mono text-[var(--color-text-secondary)]">
            <span className="flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5" />
              {new Date(createdAt).toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
            <span>·</span>
            <span>Audit ID: {auditId.slice(0, 13)}</span>
          </div>
        </div>

        {/* Right: Score Ring & Compliance Counts */}
        <div className="flex items-center gap-6 self-start md:self-center">
          {/* Circular Score Gauge */}
          <div className="relative flex items-center justify-center">
            <svg className="h-28 w-28 -rotate-90 transform" viewBox="0 0 100 100">
              {/* Background circle */}
              <circle
                cx="50"
                cy="50"
                r={radius}
                className="stroke-slate-200 dark:stroke-slate-800"
                strokeWidth="8"
                fill="transparent"
              />
              {/* Animated Progress circle */}
              <circle
                cx="50"
                cy="50"
                r={radius}
                className={`transition-all duration-1000 ease-out ${
                  score >= 80 ? 'stroke-green-500' : score >= 50 ? 'stroke-amber-500' : 'stroke-red-500'
                }`}
                strokeWidth="8"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                fill="transparent"
              />
            </svg>
            <div className="absolute flex flex-col items-center justify-center text-center">
              <span className="font-mono text-2xl font-black text-[var(--color-text)]">
                {score}
              </span>
              <span className="text-[10px] uppercase font-semibold text-[var(--color-text-secondary)]">
                Score
              </span>
            </div>
          </div>

          {/* Breakdown Counts */}
          {summary && (
            <div className="space-y-1.5 border-l border-[var(--color-border)] pl-6 text-xs">
              <div className="flex items-center gap-2 font-mono">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <span className="font-semibold text-[var(--color-text)]">{summary.pass}</span>
                <span className="text-[var(--color-text-secondary)]">Passed</span>
              </div>
              <div className="flex items-center gap-2 font-mono">
                <XCircle className="h-4 w-4 text-red-600" />
                <span className="font-semibold text-[var(--color-text)]">{summary.fail}</span>
                <span className="text-[var(--color-text-secondary)]">Violations</span>
              </div>
              <div className="flex items-center gap-2 font-mono">
                <HelpCircle className="h-4 w-4 text-amber-600" />
                <span className="font-semibold text-[var(--color-text)]">{summary.unsure}</span>
                <span className="text-[var(--color-text-secondary)]">Needs Review</span>
              </div>
              <div className="pt-1">
                <span className={`text-[11px] font-semibold ${grade.colorClass}`}>
                  {grade.label}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
