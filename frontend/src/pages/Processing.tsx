import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowRight, AlertTriangle, RefreshCw, XCircle, ArrowLeft } from 'lucide-react';
import { useAuditEvents } from '../api/sse';
import { cancelAudit } from '../api/client';
import AgentTimeline from '../components/AgentTimeline';
import Disclaimer from '../components/Disclaimer';

export default function Processing() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    events,
    isConnected,
    isCompleted,
    error,
    currentRule,
    currentTool,
    progressPercent,
    retry,
  } = useAuditEvents(id);

  const [confirmCancel, setConfirmCancel] = useState(false);
  useEffect(() => {
    if (isCompleted && id) {
      const timer = setTimeout(() => {
        navigate(`/audits/${id}`);
      }, 1200);
      return () => clearTimeout(timer);
    }
  }, [isCompleted, id, navigate]);

  async function handleCancel() {
    if (!id) return;
    try {
      await cancelAudit(id);
    } catch (err) {
      console.error('Cancel request error:', err);
    }
  }

  const isReplayRun = events.some((e) => Boolean((e.payload as any)?.is_replay));
  const sourceProviderMode = (events.find((e) => (e.payload as any)?.source_provider_mode)?.payload as any)?.source_provider_mode;
  const isLiveReplay = sourceProviderMode === 'record';

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-16">
      {/* Header */}
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Home
          </Link>
          <div className="flex items-center gap-2">
            {isReplayRun ? (
              <span className="rounded-full bg-amber-500/20 px-2.5 py-0.5 text-xs font-bold text-amber-700 dark:text-amber-400 border border-amber-500/30">
                {isLiveReplay ? 'RECORDED RUN (live providers)' : 'SIMULATED REPLAY (mock fixtures)'}
              </span>
            ) : (
              <>
                <span className={`inline-block h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-amber-500 animate-pulse'}`} />
                <span className="text-xs font-mono text-[var(--color-text-secondary)]">
                  {isConnected ? 'Live SSE Stream Active' : 'Connecting to Stream...'}
                </span>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-10 space-y-8">
        {isReplayRun && (
          <div className="flex items-center gap-2 rounded-xl bg-amber-500/10 border border-amber-500/30 px-4 py-2.5 text-xs text-amber-800 dark:text-amber-300 font-medium">
            <span className="font-bold uppercase tracking-wider text-[11px] bg-amber-500/20 px-1.5 py-0.5 rounded mr-1">
              {isLiveReplay ? 'RECORDED RUN' : 'SIMULATED REPLAY'}
            </span>
            <span>Replaying captured audit fixture with realistic timing. This run is an offline fallback, not a live execution.</span>
          </div>
        )}
        {/* Title */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <span className="text-xs font-mono uppercase tracking-wider text-[var(--color-text-secondary)]">
              Audit ID: {id}
            </span>
            <h1 className="text-2xl sm:text-3xl font-bold text-[var(--color-text)]">
              {isCompleted ? 'Audit Processing Finished' : error ? 'Audit Interrupted' : 'Agent Planning in Progress'}
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {isCompleted
                ? 'All rules evaluated. Redirecting to final pre-inspection report...'
                : error
                ? 'An error occurred during frame processing or rule validation.'
                : 'Evaluating checklist rules using grounded visual segmentation and geometric tools.'}
            </p>
          </div>

          {!isCompleted && !error && (
            confirmCancel ? (
              <div className="flex items-center gap-2 self-start sm:self-center">
                <span className="text-xs font-semibold text-rose-700 dark:text-rose-400">Cancel run?</span>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 transition-colors"
                >
                  Yes, Cancel
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmCancel(false)}
                  className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] transition-colors"
                >
                  Keep Running
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmCancel(true)}
                className="inline-flex items-center gap-1.5 self-start sm:self-center rounded-lg border border-red-200 bg-red-50 px-3.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 transition-colors"
              >
                <XCircle className="h-4 w-4" />
                Cancel Audit
              </button>
            )
          )}

          {isCompleted && id && (
            <Link
              to={`/audits/${id}`}
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-[var(--color-accent-hover)]"
            >
              <span>View Report Now</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
          )}
        </div>

        {/* Error Banner */}
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200 space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-red-600 shrink-0" />
              <span className="font-semibold text-sm">Processing Error</span>
            </div>
            <p className="font-mono text-xs opacity-90">{error}</p>
            <div className="flex gap-2 pt-1">
              <button
                onClick={retry}
                className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Retry
              </button>
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-800 hover:bg-red-50"
              >
                Back to Safety Checklists
              </Link>
            </div>
          </div>
        )}

        {/* Live Agent Timeline Component */}
        <AgentTimeline
          events={events}
          currentRule={currentRule}
          currentTool={currentTool}
          progressPercent={progressPercent}
          isCompleted={isCompleted}
          error={error}
        />

        <Disclaimer compact />
      </main>
    </div>
  );
}
