import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  Shield,
  Printer,
  ChevronDown,
  ChevronUp,
  Filter,
  DollarSign,
  ArrowLeft,
  Layers,
  Loader2,
  FileQuestion,
  PlayCircle,
  AlertCircle,
  RefreshCw,
  BarChart3,
} from 'lucide-react';
import {
  getAudit,
  getAuditCost,
  getHealth,
  createDemoAudit,
  type CostSummary,
  type HealthResponse,
} from '../api/client';
import { API_BASE_URL } from '../api/config';
import type { Audit } from '../api/types';
import SummaryCard from '../components/SummaryCard';
import VideoWithMarkers from '../components/VideoWithMarkers';
import FindingCard from '../components/FindingCard';
import Disclaimer from '../components/Disclaimer';
import ModelsUsedPanel from '../components/ModelsUsedPanel';

export interface AuditNotFoundViewProps {
  id?: string;
  onLoadDemo?: () => void;
  isStartingDemo?: boolean;
}

export function AuditNotFoundView({ id, onLoadDemo, isStartingDemo }: AuditNotFoundViewProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-bg)] px-6 py-12">
      <div className="w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center shadow-lg">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-500/10 text-amber-500 mb-5">
          <FileQuestion className="h-7 w-7" />
        </div>
        <h1 className="text-xl font-bold text-[var(--color-text)]">Audit Not Found</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)] leading-relaxed">
          The audit with ID {id ? (
            <code className="rounded bg-[var(--color-bg)] px-1.5 py-0.5 font-mono text-xs text-[var(--color-text)]">{id}</code>
          ) : (
            'specified'
          )} does not exist or has been deleted.
        </p>

        <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            to="/"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-xs font-semibold text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)] transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Home
          </Link>
          <button
            onClick={onLoadDemo}
            disabled={isStartingDemo}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-xs font-semibold text-white hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer"
          >
            {isStartingDemo ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <PlayCircle className="h-4 w-4" />
            )}
            Load Demo Audit
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Report() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [audit, setAudit] = useState<Audit | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'pass' | 'fail' | 'unsure'>('all');
  const [severityFilter, setSeverityFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all');
  const [isCostOpen, setIsCostOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isNotFound, setIsNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isStartingDemo, setIsStartingDemo] = useState(false);

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const loadAuditData = useCallback(async (auditId: string) => {
    try {
      const auditData = await getAudit(auditId);
      setAudit(auditData);
      setIsNotFound(false);
      setLoadError(null);

      // Fetch health in background
      getHealth().then(setHealth).catch(console.error);

      // Only fetch cost if audit exists and is completed or failed
      if (auditData.status === 'completed' || auditData.status === 'failed') {
        getAuditCost(auditId).then(setCostSummary).catch(console.error);
      } else if (auditData.status === 'processing') {
        // If still processing, poll every 2 seconds
        stopPolling();
        pollTimerRef.current = setTimeout(() => {
          loadAuditData(auditId);
        }, 2000);
      }
    } catch (err: any) {
      stopPolling();
      if (err?.status === 404 || err?.message?.includes('404')) {
        setIsNotFound(true);
        setLoadError('The requested audit could not be found.');
      } else {
        setLoadError(err?.message || 'Failed to load audit report.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [stopPolling]);

  useEffect(() => {
    if (!id) return;
    setIsLoading(true);
    setIsNotFound(false);
    setLoadError(null);
    loadAuditData(id);

    return () => {
      stopPolling();
    };
  }, [id, loadAuditData, stopPolling]);

  async function handleLoadDemo() {
    try {
      setIsStartingDemo(true);
      const res = await createDemoAudit('fire_exit_safety');
      navigate(`/audits/${res.id}/processing`);
    } catch (err: any) {
      alert(`Could not start demo audit: ${err.message}`);
    } finally {
      setIsStartingDemo(false);
    }
  }

  if (isNotFound) {
    return <AuditNotFoundView id={id} onLoadDemo={handleLoadDemo} isStartingDemo={isStartingDemo} />;
  }

  if (loadError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-bg)] px-6 py-12">
        <div className="w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center shadow-lg">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/10 text-rose-500 mb-5">
            <AlertCircle className="h-7 w-7" />
          </div>
          <h1 className="text-xl font-bold text-[var(--color-text)]">Failed to Load Report</h1>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)] leading-relaxed">
            {loadError}
          </p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <Link
              to="/"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-xs font-semibold text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)] transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Home
            </Link>
            <button
              onClick={() => {
                if (id) {
                  setIsLoading(true);
                  loadAuditData(id);
                }
              }}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-xs font-semibold text-white hover:opacity-90 transition-opacity cursor-pointer"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading || !audit) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent)]" />
          <p className="text-sm font-medium text-[var(--color-text-secondary)]">
            Loading audit report...
          </p>
        </div>
      </div>
    );
  }

  // Filter findings based on active tabs
  const filteredFindings = audit.findings.filter((f) => {
    if (statusFilter !== 'all' && f.status !== statusFilter) return false;
    if (severityFilter !== 'all' && f.severity !== severityFilter) return false;
    return true;
  });

  const videoUrl = audit.video_url
    ? (audit.video_url.startsWith('http') ? audit.video_url : `${API_BASE_URL}${audit.video_url}`)
    : `${API_BASE_URL}/api/audits/${id}/video`;

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      {/* Top Navbar */}
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4 sticky top-0 z-20 print:hidden">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Home
          </Link>

          <div className="flex items-center gap-3">
            <Link
              to="/eval"
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
            >
              <BarChart3 className="h-3.5 w-3.5 text-blue-500" />
              <span>Eval Benchmark</span>
            </Link>

            <Link
              to={`/compare?before=${id}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
            >
              <Layers className="h-3.5 w-3.5 text-[var(--color-accent)]" />
              <span>Compare with Re-Audit</span>
            </Link>

            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              <Printer className="h-3.5 w-3.5" />
              <span>Export PDF</span>
            </button>
          </div>
        </div>
      </header>

      {/* Printable Header (Visible only when printing) */}
      <div className="hidden print:block max-w-5xl mx-auto px-6 pt-6 pb-2 border-b border-slate-300">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-6 w-6 text-blue-700" />
            <h1 className="text-xl font-bold tracking-tight text-black">
              AuditLens Safety Verification Report
            </h1>
          </div>
          <div className="text-right">
            <span className="font-mono text-xs text-slate-500 block">
              Generated: {new Date().toLocaleDateString()}
            </span>
            <span className="font-mono text-[10px] uppercase font-bold text-slate-700">
              Provider Mode: {(audit.provider_mode || health?.provider_mode || 'MOCK').toUpperCase()}
              {audit.is_replay ? ' (RECORDED RUN)' : ''}
            </span>
            <span className="font-mono text-[9px] text-slate-600 block">
              Models: {audit.model_segmentation || 'SAM 3.1'} (Seg) • {audit.model_agent || 'Muse Spark'} (Agent) • {audit.model_transcription || 'Muse Voice Transcribe'} (Audio)
            </span>
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
        {/* On-screen Provider Mode & Model Stamp Banner */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-xs font-mono">
          <div className="flex flex-wrap items-center gap-2 text-[var(--color-text-secondary)]">
            <span>Provider Mode:</span>
            <span className="font-bold text-[var(--color-text)] uppercase">
              {audit.provider_mode || health?.provider_mode || 'MOCK'}
            </span>
            {audit.is_replay && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-400 border border-amber-500/30">
                RECORDED RUN
              </span>
            )}
            <span className="text-[11px] text-[var(--color-text-secondary)]">
              ({audit.model_segmentation || 'SAM 3.1'} • {audit.model_agent || 'Muse Spark'} • {audit.model_transcription || 'Muse Voice Transcribe'})
            </span>
          </div>
          <span className="text-[11px] text-[var(--color-text-secondary)]">
            Audit ID: {audit.id.slice(0, 14)}
          </span>
        </div>

        {/* Models Used & Provider Evidence Panel (Shown on screen and in print view) */}
        <ModelsUsedPanel
          costSummary={costSummary}
          providerMode={audit.provider_mode || health?.provider_mode || 'mock'}
          models={{
            segmentation: audit.model_segmentation,
            agent: audit.model_agent,
            transcription: audit.model_transcription,
          }}
          isReplay={audit.is_replay}
        />

        {/* Summary Card with Circular Gauge */}
        <SummaryCard
          summary={audit.summary}
          templateId={audit.template_id}
          auditId={audit.id}
          createdAt={audit.created_at}
          isReplay={audit.is_replay}
          providerMode={audit.provider_mode || health?.provider_mode}
        />

        {/* Video Scrubber & Overlays (Hidden in Print) */}
        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-[var(--color-text)] flex items-center gap-2 print:hidden">
            <span>Synchronized Walkthrough Footage & Overlays</span>
            <span className="text-xs font-normal text-[var(--color-text-secondary)]">
              (click any timeline marker to seek)
            </span>
          </h3>
          <VideoWithMarkers
            videoUrl={videoUrl}
            findings={audit.findings}
            selectedFindingId={selectedFindingId}
            onSelectFinding={(fId) => setSelectedFindingId(fId)}
          />
        </section>

        {/* Checklist Findings Section */}
        <section className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--color-border)] pb-3">
            <div>
              <h2 className="text-lg font-bold text-[var(--color-text)]">
                Inspection Findings & Evidence ({filteredFindings.length})
              </h2>
              <p className="text-xs text-[var(--color-text-secondary)]">
                Each rule status is backed by code measurements or visual detections.
              </p>
            </div>

            {/* Filter Tabs (Hidden in Print) */}
            <div className="flex flex-wrap items-center gap-2 print:hidden">
              <div className="flex items-center gap-1">
                <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
                  <Filter className="h-3 w-3" /> Status:
                </span>
                {(['all', 'pass', 'fail', 'unsure'] as const).map((st) => (
                  <button
                    key={st}
                    onClick={() => setStatusFilter(st)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                      statusFilter === st
                        ? 'bg-[var(--color-accent)] text-white'
                        : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] border border-[var(--color-border)]'
                    }`}
                  >
                    {st === 'all' ? 'All' : st === 'pass' ? 'Pass' : st === 'fail' ? 'Fail' : 'Review'}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1">
                <span className="text-xs text-[var(--color-text-secondary)]">Severity:</span>
                {(['all', 'high', 'medium', 'low'] as const).map((sev) => (
                  <button
                    key={sev}
                    onClick={() => setSeverityFilter(sev)}
                    className={`rounded-lg px-2 py-1 text-xs font-medium transition-colors ${
                      severityFilter === sev
                        ? 'bg-slate-700 text-white dark:bg-slate-300 dark:text-black'
                        : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] border border-[var(--color-border)]'
                    }`}
                  >
                    {sev.charAt(0).toUpperCase() + sev.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Finding Cards List */}
          <div className="space-y-4">
            {filteredFindings.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[var(--color-border)] p-8 text-center text-xs text-[var(--color-text-secondary)]">
                No findings match the selected filter.
              </div>
            ) : (
              filteredFindings.map((f) => (
                <FindingCard
                  key={f.id}
                  finding={f}
                  isSelected={f.id === selectedFindingId}
                  onSelect={() => setSelectedFindingId(f.id)}
                />
              ))
            )}
          </div>
        </section>

        {/* Collapsible Provider Cost & Calls Panel */}
        {costSummary && (
          <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-sm print:hidden">
            <button
              type="button"
              onClick={() => setIsCostOpen(!isCostOpen)}
              className="w-full flex items-center justify-between p-4 text-xs font-semibold text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)] transition-colors"
            >
              <div className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-[var(--color-accent)]" />
                <span>Provider Usage Accounting & Estimated Costs</span>
                <span className="font-mono text-green-700 dark:text-green-400 font-bold ml-1">
                  (${costSummary.total_cost_usd.toFixed(4)} USD)
                </span>
              </div>
              {isCostOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>

            {isCostOpen && (
              <div className="border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4 text-xs space-y-3 font-mono">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div className="rounded-lg bg-[var(--color-surface)] p-3 border border-[var(--color-border)]">
                    <span className="text-[var(--color-text-secondary)] block text-[11px]">Total Calls</span>
                    <span className="text-base font-bold text-[var(--color-text)]">{costSummary.total_calls}</span>
                  </div>
                  <div className="rounded-lg bg-[var(--color-surface)] p-3 border border-[var(--color-border)]">
                    <span className="text-[var(--color-text-secondary)] block text-[11px]">Est. Cost USD</span>
                    <span className="text-base font-bold text-green-700 dark:text-green-400">
                      ${costSummary.total_cost_usd.toFixed(4)}
                    </span>
                  </div>
                  <div className="rounded-lg bg-[var(--color-surface)] p-3 border border-[var(--color-border)] col-span-2 sm:col-span-1">
                    <span className="text-[var(--color-text-secondary)] block text-[11px]">Billing Mode</span>
                    <span className="text-sm font-semibold text-[var(--color-text)]">Mock Estimator</span>
                  </div>
                </div>

                <div className="space-y-1.5 pt-1">
                  <span className="text-[11px] font-semibold text-[var(--color-text-secondary)] uppercase">
                    Provider Breakdown:
                  </span>
                  {Object.entries(costSummary.by_provider).map(([prov, pData]) => (
                    <div key={prov} className="flex justify-between text-xs py-1 border-b border-[var(--color-border)] last:border-0">
                      <span>{prov}</span>
                      <span>
                        {pData.calls} calls ({pData.units} units) → ${pData.cost_usd.toFixed(4)}
                      </span>
                    </div>
                  ))}
                </div>

                <p className="text-[10px] text-[var(--color-text-secondary)] italic pt-1">
                  * Note: Uses UNIT_PRICE_* placeholder rates. Will update automatically upon Meta official API pricing release.
                </p>
              </div>
            )}
          </section>
        )}

        {/* Footer Disclaimer */}
        <Disclaimer />
      </main>
    </div>
  );
}
