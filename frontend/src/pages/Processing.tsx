import { useEffect } from 'react';
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

  // Auto-navigate to report on completion
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
    if (window.confirm('Are you sure you want to cancel this audit run?')) {
      try {
        await cancelAudit(id);
      } catch (err) {
        console.error('Cancel request error:', err);
      }
    }
  }

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
            <span className={`inline-block h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-amber-500 animate-pulse'}`} />
            <span className="text-xs font-mono text-[var(--color-text-secondary)]">
              {isConnected ? 'Live SSE Stream Active' : 'Connecting to Stream...'}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-10 space-y-8">
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
                ? 'All rules evaluated. Redirecting to final compliance report...'
                : error
                ? 'An error occurred during frame processing or rule validation.'
                : 'Evaluating checklist rules using grounded visual segmentation and geometric tools.'}
            </p>
          </div>

          {!isCompleted && !error && (
            <button
              onClick={handleCancel}
              className="inline-flex items-center gap-1.5 self-start sm:self-center rounded-lg border border-red-200 bg-red-50 px-3.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 transition-colors"
            >
              <XCircle className="h-4 w-4" />
              Cancel Audit
            </button>
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
