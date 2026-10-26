import { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  HelpCircle,
  Clock,
  Ruler,
  Wrench,
  Maximize2,
  X,
  Mic,
  Camera,
  Cpu,
} from 'lucide-react';
import type { Finding } from '../api/types';
import { formatTimestamp, getSeverityMeta, getStatusMeta } from '../utils/formatters';

interface FindingCardProps {
  finding: Finding;
  isSelected?: boolean;
  onSelect?: () => void;
}

export default function FindingCard({
  finding,
  isSelected = false,
  onSelect,
}: FindingCardProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const statusMeta = getStatusMeta(finding.status);
  const severityMeta = getSeverityMeta(finding.severity);

  const rawMeas = finding.measurement as any;

  function renderStatusIcon() {
    switch (finding.status) {
      case 'pass':
        return <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />;
      case 'fail':
        return <XCircle className="h-4 w-4 shrink-0 text-red-600" />;
      case 'unsure':
      default:
        return <HelpCircle className="h-4 w-4 shrink-0 text-amber-600" />;
    }
  }

  function renderSourceIcon(src: string) {
    if (src === 'voice_note') return <Mic className="h-3 w-3" />;
    if (src === 'measurement') return <Ruler className="h-3 w-3" />;
    if (src === 'code') return <Cpu className="h-3 w-3" />;
    return <Camera className="h-3 w-3" />;
  }

  return (
    <>
      <div
        onClick={onSelect}
        className={`rounded-xl border bg-[var(--color-surface)] p-5 transition-all cursor-pointer ${
          isSelected
            ? 'border-[var(--color-accent)] ring-2 ring-[var(--color-accent)]/20 shadow-md'
            : 'border-[var(--color-border)] hover:border-slate-300 shadow-sm'
        } print:border-slate-300 print:shadow-none print:break-inside-avoid`}
      >
        <div className="space-y-4">
          {/* Header Row: Status, Rule ID, Severity, Confidence, Timestamp */}
          <div className="flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statusMeta.badgeClass}`}>
                {renderStatusIcon()}
                {statusMeta.label}
              </span>
              <span className="font-semibold text-sm text-[var(--color-text)]">
                {finding.rule_id}
              </span>
            </div>

            <div className="flex items-center gap-2 text-xs font-mono">
              <span className={`rounded px-2 py-0.5 text-[11px] font-medium ${severityMeta.badge}`}>
                {severityMeta.label}
              </span>
              <span className="text-[var(--color-text-secondary)]">·</span>
              <span className="font-medium text-[var(--color-text)]">
                {Math.round(finding.confidence * 100)}% conf
              </span>
              <span className="text-[var(--color-text-secondary)]">·</span>
              <span className="inline-flex items-center gap-1 text-[var(--color-text-secondary)]">
                <Clock className="h-3 w-3" />
                {formatTimestamp(finding.timestamp_s)}
              </span>
            </div>
          </div>

          {/* Rationale & Observation */}
          <p className="text-sm text-[var(--color-text)] leading-relaxed">
            {finding.rationale}
          </p>

          {/* Measurement Details (if present) */}
          {rawMeas && rawMeas.width_m !== undefined && (
            <div className="rounded-lg bg-[var(--color-bg-secondary)] p-3 text-xs space-y-1.5 border border-[var(--color-border)]">
              <div className="flex items-center justify-between font-mono font-medium text-[var(--color-text)]">
                <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                  <Ruler className="h-3.5 w-3.5" />
                  Estimated Clear Width:
                </span>
                <span className="text-sm font-bold">
                  {rawMeas.width_m.toFixed(2)} m (± {rawMeas.uncertainty_m?.toFixed(2)} m)
                </span>
              </div>
              {rawMeas.method && (
                <p className="text-[11px] text-[var(--color-text-secondary)]">
                  <strong>Calibration Method:</strong> {rawMeas.method}
                </p>
              )}
              {rawMeas.assumptions && (
                <p className="text-[11px] text-[var(--color-text-secondary)] italic">
                  <strong>Assumptions & Limits:</strong> {rawMeas.assumptions}
                </p>
              )}
            </div>
          )}

          {/* Unsure Guidance Panel */}
          {finding.status === 'unsure' && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200 space-y-1">
              <span className="font-semibold flex items-center gap-1.5">
                <HelpCircle className="h-3.5 w-3.5 text-amber-600" />
                What Footage Would Resolve This?
              </span>
              <p className="text-[11px] text-amber-800 dark:text-amber-300/90 leading-relaxed">
                Capture close-up, steady footage with the target object centered and unobstructed.
                Ensure consistent lighting and keep an A4 reference sheet in view at the same depth plane.
              </p>
            </div>
          )}

          {/* Fix Action Recommendation */}
          {finding.fix_text && (
            <div className="rounded-lg border border-red-100 bg-red-50/60 p-3 text-xs text-red-900 dark:border-red-950 dark:bg-red-950/30 dark:text-red-200 space-y-1">
              <span className="font-semibold flex items-center gap-1.5">
                <Wrench className="h-3.5 w-3.5 text-red-600" />
                Recommended Corrective Fix:
              </span>
              <p className="text-[11px] leading-relaxed opacity-95">
                {finding.fix_text}
              </p>
            </div>
          )}

          {/* Evidence Image Thumbnail and Evidence Source Badges */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1 border-t border-[var(--color-border)]">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setIsModalOpen(true);
                }}
                className="group relative flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-1.5 hover:border-[var(--color-accent)] transition-colors"
              >
                <img
                  src={finding.overlay_url}
                  alt={`Evidence overlay for ${finding.rule_id}`}
                  loading="lazy"
                  className="h-10 w-16 rounded object-cover bg-black"
                />
                <span className="text-xs text-[var(--color-text-secondary)] font-medium group-hover:text-[var(--color-accent)] pr-1 flex items-center gap-1">
                  <Maximize2 className="h-3 w-3" />
                  View Overlay
                </span>
              </button>
            </div>

            {/* Source Badges */}
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-[var(--color-text-secondary)] uppercase tracking-wider mr-1">
                Sources:
              </span>
              {finding.sources.map((src, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 rounded bg-[var(--color-bg-secondary)] px-2 py-0.5 text-[10px] font-mono text-[var(--color-text-secondary)]"
                >
                  {renderSourceIcon(src)}
                  {src.replace('_', ' ')}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Enlarged Image Modal */}
      {isModalOpen && (
        <div
          onClick={() => setIsModalOpen(false)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 print:hidden"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative max-h-[90vh] max-w-4xl overflow-hidden rounded-2xl bg-black shadow-2xl border border-slate-700"
          >
            <div className="flex items-center justify-between bg-slate-900 px-4 py-3 text-white text-xs border-b border-slate-800">
              <span className="font-mono font-medium">
                {finding.rule_id} · Overlay Evidence #{finding.frame_idx}
              </span>
              <button
                onClick={() => setIsModalOpen(false)}
                className="rounded p-1 text-slate-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <img
              src={finding.overlay_url}
              alt="Enlarged overlay"
              className="max-h-[80vh] w-auto object-contain mx-auto"
            />
          </div>
        </div>
      )}
    </>
  );
}
