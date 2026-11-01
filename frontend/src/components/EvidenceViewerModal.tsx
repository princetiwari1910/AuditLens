import { useEffect, useCallback } from 'react';
import {
  X,
  Play,
  ShieldCheck,
  Eye,
  Mic,
  Layers,
  ChevronLeft,
  ChevronRight,
  Activity,
  AlertTriangle,
} from 'lucide-react';
import type { Finding } from '../api/types';
import { API_BASE_URL } from '../api/config';
import { formatTimestamp, getSeverityMeta, getStatusMeta } from '../utils/formatters';

interface EvidenceViewerModalProps {
  finding: Finding | null;
  isOpen: boolean;
  onClose: () => void;
  onNavigateNext?: () => void;
  onNavigatePrev?: () => void;
  onSeekVideo?: (timestamp_s: number) => void;
}

export default function EvidenceViewerModal({
  finding,
  isOpen,
  onClose,
  onNavigateNext,
  onNavigatePrev,
  onSeekVideo,
}: EvidenceViewerModalProps) {
  // Keyboard navigation handler (j/k, Enter, Esc)
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen || !finding) return;

      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'j' || e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        onNavigateNext?.();
      } else if (e.key === 'k' || e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        onNavigatePrev?.();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        onSeekVideo?.(finding.timestamp_s);
      }
    },
    [isOpen, finding, onClose, onNavigateNext, onNavigatePrev, onSeekVideo]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!isOpen || !finding) return null;

  const statusMeta = getStatusMeta(finding.status);
  const severityMeta = getSeverityMeta(finding.severity);

  const overlaySrc = finding.overlay_url
    ? finding.overlay_url.startsWith('http')
      ? finding.overlay_url
      : `${API_BASE_URL}${finding.overlay_url}`
    : '';

  const strongest = finding.strongest_evidence;
  const strength = strongest?.strength || (finding.sources.includes('voice_note') ? 'voice_note' : 'mask_backed');

  function renderStrengthBadge() {
    switch (strength) {
      case 'mask_backed':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <ShieldCheck className="h-3.5 w-3.5" />
            Mask-Backed Visual Evidence
          </span>
        );
      case 'model_attested':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/10 px-2.5 py-1 text-xs font-semibold text-blue-600 dark:text-blue-400 border border-blue-500/20">
            <Eye className="h-3.5 w-3.5" />
            Model-Attested Detection
          </span>
        );
      case 'voice_note':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-purple-500/10 px-2.5 py-1 text-xs font-semibold text-purple-600 dark:text-purple-400 border border-purple-500/20">
            <Mic className="h-3.5 w-3.5" />
            Voice Note Evidence
          </span>
        );
      default:
        return null;
    }
  }

  const evidenceLedger = finding.evidence_ledger || [];
  const escalationSteps = finding.escalation_steps || [];

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 print:hidden overflow-y-auto"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative my-8 w-full max-w-4xl overflow-hidden rounded-2xl bg-[var(--color-surface)] shadow-2xl border border-[var(--color-border)] text-[var(--color-text)]"
      >
        {/* Header Bar */}
        <div className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg)] px-6 py-4">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statusMeta.badgeClass}`}
            >
              {statusMeta.label}
            </span>
            <h2 className="text-base font-bold font-mono text-[var(--color-text)]">
              {finding.rule_id}
            </h2>
            <span className={`rounded px-2 py-0.5 text-[11px] font-medium ${severityMeta.badge}`}>
              {severityMeta.label}
            </span>
            <span className="text-xs text-[var(--color-text-secondary)]">
              ({Math.round(finding.confidence * 100)}% confidence)
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onNavigatePrev}
              title="Previous Finding [k]"
              className="rounded-lg p-1.5 text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button
              onClick={onNavigateNext}
              title="Next Finding [j]"
              className="rounded-lg p-1.5 text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
            <div className="h-4 w-px bg-[var(--color-border)] mx-1" />
            <button
              onClick={onClose}
              title="Close [Esc]"
              className="rounded-lg p-1.5 text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text)]"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">
          {/* Main Visual & Best Frame */}
          <div className="space-y-3">
            <div className="relative rounded-xl overflow-hidden bg-black aspect-video flex items-center justify-center border border-slate-800">
              {overlaySrc ? (
                <img
                  src={overlaySrc}
                  alt={`Evidence frame for ${finding.rule_id}`}
                  className="max-h-full max-w-full object-contain"
                />
              ) : (
                <div className="text-xs text-slate-500">No frame preview available</div>
              )}

              {/* Timestamp & Video Seek Quick Action */}
              <div className="absolute bottom-3 left-3 flex items-center gap-2">
                <button
                  onClick={() => onSeekVideo?.(finding.timestamp_s)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-black/75 backdrop-blur-md px-3 py-1.5 text-xs font-semibold text-white hover:bg-black/90 transition-colors border border-white/20"
                >
                  <Play className="h-3.5 w-3.5 text-[var(--color-accent)]" />
                  <span>Seek Video ({formatTimestamp(finding.timestamp_s)})</span>
                </button>
              </div>

              {/* Overlay Badge Top Right */}
              <div className="absolute top-3 right-3">
                {renderStrengthBadge()}
              </div>
            </div>

            {/* Tracking stability & temporal support info */}
            {finding.support_count !== undefined && (
              <div className="flex flex-wrap items-center justify-between text-xs text-[var(--color-text-secondary)] bg-[var(--color-bg)] p-3 rounded-xl border border-[var(--color-border)]">
                <span className="flex items-center gap-1.5">
                  <Activity className="h-4 w-4 text-[var(--color-accent)]" />
                  <strong>Temporal Tracking:</strong> Observed across {finding.support_count} keyframe(s)
                </span>
                <span className="font-mono">
                  Stability Score: {((finding.stability ?? 1.0) * 100).toFixed(0)}% · Decision Policy: {finding.decision_policy || 'standard'}
                </span>
              </div>
            )}
          </div>

          {/* Reasoning & Rationale */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
              Perception Reasoning & Evidence Rationale
            </h3>
            <div className="p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-sm leading-relaxed">
              {finding.rationale}
            </div>
          </div>

          {/* Cited Frames Strip */}
          {evidenceLedger.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)] flex items-center gap-2">
                <Layers className="h-3.5 w-3.5" />
                <span>Cited Keyframes ({evidenceLedger.length})</span>
              </h3>
              <div className="flex gap-2 overflow-x-auto pb-2">
                {evidenceLedger.map((ev, i) => (
                  <button
                    key={ev.id || i}
                    onClick={() => onSeekVideo?.(ev.ts)}
                    className="flex-shrink-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-2 hover:border-[var(--color-accent)] transition-all text-left space-y-1"
                  >
                    <div className="flex items-center justify-between text-[10px] font-mono gap-2 text-[var(--color-text-secondary)]">
                      <span>#{ev.frame_id}</span>
                      <span>{formatTimestamp(ev.ts)}</span>
                    </div>
                    <div className="text-[11px] font-semibold text-[var(--color-text)] truncate max-w-[120px]">
                      {ev.concept}
                    </div>
                    <div className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">
                      {(ev.score * 100).toFixed(0)}% conf
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Active Gathering / Why Unsure Escalation Section */}
          {(finding.status === 'unsure' || escalationSteps.length > 0) && (
            <div className="space-y-3 p-4 rounded-xl border border-amber-500/30 bg-amber-500/5">
              <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400 font-semibold text-xs">
                <AlertTriangle className="h-4 w-4" />
                <span>Active Evidence Gathering & Escalation Trace</span>
              </div>
              {escalationSteps.length > 0 ? (
                <div className="space-y-2">
                  {escalationSteps.map((step, idx) => (
                    <div
                      key={idx}
                      className="text-xs flex items-center justify-between p-2 rounded bg-[var(--color-surface)] border border-[var(--color-border)]"
                    >
                      <span className="font-mono text-[var(--color-text-secondary)]">
                        Step {step.step}: {step.action}
                      </span>
                      <span className="font-semibold text-[var(--color-text)]">
                        {step.outcome}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
                  No confident detection met the safety compliance threshold. Escalation steps were bounded to preserve budget.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer with Keyboard Shortcuts Legend */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] bg-[var(--color-bg)] px-6 py-3 text-xs text-[var(--color-text-secondary)] font-mono">
          <div className="flex items-center gap-4">
            <span><kbd className="px-1.5 py-0.5 rounded bg-[var(--color-surface)] border border-[var(--color-border)]">j / k</kbd> Next / Prev</span>
            <span><kbd className="px-1.5 py-0.5 rounded bg-[var(--color-surface)] border border-[var(--color-border)]">Enter</kbd> Seek video</span>
            <span><kbd className="px-1.5 py-0.5 rounded bg-[var(--color-surface)] border border-[var(--color-border)]">Esc</kbd> Close</span>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] px-3 py-1 font-semibold text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
