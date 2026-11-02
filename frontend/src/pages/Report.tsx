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
  Activity,
  Share2,
  FileText,
  Download,
} from 'lucide-react';
import {
  getAudit,
  getSharedAudit,
  getAuditCost,
  getHealth,
  getAuditLog,
  createDemoAudit,
  createShareLink,
  type CostSummary,
  type HealthResponse,
  type AuditLogEntry,
} from '../api/client';
import { API_BASE_URL } from '../api/config';
import type { Audit } from '../api/types';
import SummaryCard from '../components/SummaryCard';
import VideoWithMarkers from '../components/VideoWithMarkers';
import FindingCard from '../components/FindingCard';
import Disclaimer from '../components/Disclaimer';
import ModelsUsedPanel from '../components/ModelsUsedPanel';
import PrivacyBadge from '../components/PrivacyBadge';
import EvidenceViewerModal from '../components/EvidenceViewerModal';
import ReviewQueuePanel from '../components/ReviewQueuePanel';
import FixPlanSection from '../components/FixPlanSection';

export interface AuditNotFoundViewProps {
  id?: string;
  onLoadDemo?: () => void;
  isStartingDemo?: boolean;
  demoError?: string | null;
  onDismissError?: () => void;
}

export function AuditNotFoundView({
  id,
  onLoadDemo,
  isStartingDemo,
  demoError,
  onDismissError,
}: AuditNotFoundViewProps) {
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

        {demoError && (
          <div role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200 text-left">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-rose-600 mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="font-semibold">Could not start demo audit</p>
                <p className="font-mono text-[11px] mt-0.5 text-rose-700 dark:text-rose-300">{demoError}</p>
              </div>
              {onDismissError && (
                <button
                  type="button"
                  onClick={onDismissError}
                  className="text-rose-500 hover:text-rose-700 text-xs font-bold"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        )}

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

export interface ReportProps {
  isShared?: boolean;
  initialAudit?: Audit | null;
}

export default function Report({ isShared = false, initialAudit = null }: ReportProps = {}) {
  const { id, token } = useParams<{ id?: string; token?: string }>();
  const navigate = useNavigate();

  const isReadOnly = isShared || Boolean(token);
  const activeIdentifier = token || id;
  const isTokenRequest = Boolean(token);

  const [audit, setAudit] = useState<Audit | null>(initialAudit);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [isEvidenceModalOpen, setIsEvidenceModalOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<'all' | 'pass' | 'fail' | 'unsure' | 'needs_review'>('all');
  const [severityFilter, setSeverityFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all');
  const [isCostOpen, setIsCostOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(!initialAudit);
  const [isNotFound, setIsNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isStartingDemo, setIsStartingDemo] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [reviewingFindingId, setReviewingFindingId] = useState<string | null>(null);
  const [shareCopied, setShareCopied] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const loadAuditData = useCallback(async (identifier: string, isToken: boolean = false) => {
    try {
      const auditData = isToken ? await getSharedAudit(identifier) : await getAudit(identifier);
      setAudit(auditData);
      setIsNotFound(false);
      setLoadError(null);

      // Fetch health in background
      getHealth().then(setHealth).catch(console.error);

      if (!isToken) {
        getAuditLog(identifier).then(setAuditLogs).catch(console.error);
        if (auditData.status === 'completed' || auditData.status === 'failed') {
          getAuditCost(identifier).then(setCostSummary).catch(console.error);
        } else if (auditData.status === 'processing') {
          stopPolling();
          pollTimerRef.current = setTimeout(() => {
            loadAuditData(identifier, isToken);
          }, 2000);
        }
      } else {
        if (auditData.status === 'completed' || auditData.status === 'failed') {
          getAuditCost(auditData.id).then(setCostSummary).catch(console.error);
        }
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
    if (initialAudit) {
      return;
    }
    if (!activeIdentifier) {
      setIsNotFound(true);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setIsNotFound(false);
    setLoadError(null);
    loadAuditData(activeIdentifier, isTokenRequest);

    return () => {
      stopPolling();
    };
  }, [activeIdentifier, isTokenRequest, loadAuditData, stopPolling, initialAudit]);

  async function handleLoadDemo() {
    try {
      setDemoError(null);
      setIsStartingDemo(true);
      const res = await createDemoAudit('campus_fire_exit_core');
      navigate(`/audits/${res.id}/processing`);
    } catch (err: any) {
      setDemoError(err.message || 'Could not start demo audit');
    } finally {
      setIsStartingDemo(false);
    }
  }

  if (isNotFound) {
    return (
      <AuditNotFoundView
        id={activeIdentifier}
        onLoadDemo={handleLoadDemo}
        isStartingDemo={isStartingDemo}
        demoError={demoError}
        onDismissError={() => setDemoError(null)}
      />
    );
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
                if (activeIdentifier) {
                  setIsLoading(true);
                  loadAuditData(activeIdentifier, isTokenRequest);
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
  const findings = audit.findings || [];
  const needsReviewCount = findings.filter(
    (f) => f.status === 'unsure' || f.ai_verdict === 'unsure' || f.final_verdict === 'unsure'
  ).length;

  const filteredFindings = findings.filter((f) => {
    if (statusFilter === 'needs_review') {
      const needs = f.status === 'unsure' || f.ai_verdict === 'unsure' || f.final_verdict === 'unsure';
      if (!needs) return false;
    } else if (statusFilter !== 'all' && f.status !== statusFilter) {
      return false;
    }
    if (severityFilter !== 'all' && f.severity !== severityFilter) return false;
    return true;
  });

  const handleReviewSuccess = (
    findingId: string,
    res: any,
    newSummary: any,
    newLogEntry: AuditLogEntry
  ) => {
    setAudit((prev) => {
      if (!prev) return prev;
      const updatedFindings = (prev.findings || []).map((f) =>
        f.id === findingId
          ? {
              ...f,
              status: res.status,
              ai_verdict: res.ai_verdict,
              final_verdict: res.final_verdict,
            }
          : f
      );
      return {
        ...prev,
        findings: updatedFindings,
        summary: newSummary || prev.summary,
      };
    });
    setAuditLogs((prev) => [newLogEntry, ...prev]);
  };

  const selectedFinding = findings.find((f) => f.id === selectedFindingId) || null;

  const handleSelectFinding = (findingId: string) => {
    setSelectedFindingId(findingId);
    setIsEvidenceModalOpen(true);
  };

  const handleNavigateNext = () => {
    if (!selectedFindingId || filteredFindings.length === 0) return;
    const currentIndex = filteredFindings.findIndex((f) => f.id === selectedFindingId);
    const nextIndex = (currentIndex + 1) % filteredFindings.length;
    setSelectedFindingId(filteredFindings[nextIndex].id);
  };

  const handleNavigatePrev = () => {
    if (!selectedFindingId || filteredFindings.length === 0) return;
    const currentIndex = filteredFindings.findIndex((f) => f.id === selectedFindingId);
    const prevIndex = (currentIndex - 1 + filteredFindings.length) % filteredFindings.length;
    setSelectedFindingId(filteredFindings[prevIndex].id);
  };

  const handleShare = async () => {
    if (!id) return;
    try {
      setShareError(null);
      const res = await createShareLink(id);
      const fullUrl = `${window.location.origin}${res.share_url}`;
      await navigator.clipboard.writeText(fullUrl);
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 3000);
    } catch (err: any) {
      setShareError(err?.message || 'Could not create share link');
      setTimeout(() => setShareError(null), 5000);
    }
  };

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

          <div className="flex items-center gap-2.5">
            {isReadOnly && (
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-mono font-semibold text-blue-700 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-300">
                <Shield className="h-3.5 w-3.5" />
                Read-Only Share
              </span>
            )}

            {!isReadOnly && (
              <Link
                to={`/audits/${id}/trace`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
              >
                <Activity className="h-3.5 w-3.5 text-emerald-500" />
                <span className="hidden sm:inline">Trace</span>
              </Link>
            )}

            {!isReadOnly && (
              <>
                <button
                  onClick={handleShare}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
                >
                  <Share2 className="h-3.5 w-3.5 text-blue-500" />
                  <span>{shareCopied ? 'Copied!' : 'Share'}</span>
                </button>
                {shareError && (
                  <span className="text-[11px] font-medium text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950 px-2 py-1 rounded border border-rose-200 dark:border-rose-800">
                    {shareError}
                  </span>
                )}
              </>
            )}

            <a
              href={`${API_BASE_URL}/api/audits/${audit.id}/bundle`}
              download={`audit-${audit.id}-evidence.zip`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)] transition-colors"
              title="Download SHA-256 verified evidence bundle"
            >
              <Download className="h-3.5 w-3.5 text-indigo-500" />
              <span>Evidence bundle (.zip)</span>
            </a>

            <Link
              to="/eval"
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
            >
              <BarChart3 className="h-3.5 w-3.5 text-blue-500" />
              <span className="hidden sm:inline">Eval Benchmark</span>
            </Link>

            {!isReadOnly && (
              <Link
                to={`/compare?before=${id}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
              >
                <Layers className="h-3.5 w-3.5 text-[var(--color-accent)]" />
                <span className="hidden sm:inline">Compare</span>
              </Link>
            )}

            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              <Printer className="h-3.5 w-3.5" />
              <span>Export PDF</span>
            </button>
          </div>
        </div>
        <div className="mx-auto max-w-5xl pt-1 flex justify-end">
          <p className="text-[11px] text-[var(--color-text-secondary)] font-mono">
            Integrity check: scripts/verify_bundle.py checks the hashes.
          </p>
        </div>
      </header>

      {/* Printable Header (Visible only when printing) */}
      <div className="hidden print:block max-w-5xl mx-auto px-6 pt-6 pb-2 border-b border-slate-300">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-6 w-6 text-blue-700" />
            <h1 className="text-xl font-bold tracking-tight text-black">
              AuditLens Pre-Inspection Report
            </h1>
          </div>
          <div className="text-right">
            <span className="font-mono text-xs text-slate-500 block">
              Generated: {new Date().toLocaleDateString()}
            </span>
            <span className="font-mono text-[10px] uppercase font-bold text-slate-700">
              Provider Mode: {(audit.provider_mode || health?.provider_mode || 'MOCK').toUpperCase()}
              {audit.is_replay ? (audit.source_provider_mode === 'record' ? ' (RECORDED RUN - LIVE PROVIDERS)' : ' (SIMULATED REPLAY - MOCK FIXTURES)') : ''}
            </span>
            <span className="font-mono text-[9px] text-slate-600 block">
              {audit.source_provider_mode !== 'record' || (!audit.is_replay && (audit.provider_mode || health?.provider_mode) === 'mock')
                ? 'Models: simulated stand-ins for SAM 3.1 / Muse Spark / Muse Voice • Stored frames and exported evidence are blurred (best effort). The original upload is kept for playback and frames are sent to the model before blurring.'
                : `Models: ${audit.model_segmentation || 'SAM 3.1'} (Seg) • ${audit.model_agent || 'Muse Spark'} (Agent) • ${audit.model_transcription || 'Muse Voice Transcribe'} (Audio) • Stored frames and exported evidence are blurred (best effort). The original upload is kept for playback and frames are sent to the model before blurring.`}
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
                {audit.source_provider_mode === 'record' ? 'RECORDED RUN (live providers)' : 'SIMULATED REPLAY (mock fixtures)'}
              </span>
            )}
            <span className="text-[11px] text-[var(--color-text-secondary)]">
              {audit.source_provider_mode !== 'record' || (!audit.is_replay && (audit.provider_mode || health?.provider_mode) === 'mock')
                ? '(simulated stand-ins for SAM 3.1 / Muse Spark / Muse Voice)'
                : `(${audit.model_segmentation || 'SAM 3.1'} • ${audit.model_agent || 'Muse Spark'} • ${audit.model_transcription || 'Muse Voice Transcribe'})`}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[var(--color-text-secondary)]">
              {`Audit ID: ${(audit.id || '').slice(0, 14)}`}
            </span>
          </div>
        </div>

        {/* Privacy Note Banner */}
        <PrivacyBadge />

        {/* Executive Summary Block (WP14) */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-2 shadow-sm print:border-slate-300 print:break-inside-avoid">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)] flex items-center gap-1.5">
              <FileText className="h-4 w-4 text-[var(--color-accent)]" />
              Executive Pre-Inspection Summary
            </span>
            <span className="text-xs font-mono text-[var(--color-text-secondary)]">
              {audit.created_at ? new Date(audit.created_at).toLocaleDateString() : 'Recent'}
            </span>
          </div>
          {(() => {
            const framesCount = audit.summary?.frames_analyzed ?? 12;
            const framesUnit = framesCount === 1 ? 'visual keyframe' : 'visual keyframes';
            const passCount = audit.summary?.pass || 0;
            const failCount = audit.summary?.fail || 0;
            const unsureCount = audit.summary?.unsure || 0;
            const failUnit = failCount === 1 ? 'finding' : 'findings';
            const unsureUnit = unsureCount === 1 ? 'item' : 'items';
            return (
              <p className="text-xs sm:text-sm text-[var(--color-text)] leading-relaxed">
                AuditLens assistive safety pre-audit completed for template <code className="font-mono text-xs bg-[var(--color-bg)] px-1.5 py-0.5 rounded font-semibold">{audit.template_id || 'general'}</code> across {framesCount} {framesUnit}.
                Overall pre-inspection score is <strong className="font-mono text-[var(--color-accent)]">{audit.summary?.score ?? 0}/100</strong> with {passCount} passed, {failCount} {failUnit} needing attention, and {unsureCount} {unsureUnit} pending review.
              </p>
            );
          })()}
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
          sourceProviderMode={audit.source_provider_mode}
        />

        {/* Summary Card with Circular Gauge */}
        <SummaryCard
          summary={audit.summary}
          templateId={audit.template_id}
          auditId={audit.id}
          createdAt={audit.created_at}
          isReplay={audit.is_replay}
          providerMode={audit.provider_mode || health?.provider_mode}
          sourceProviderMode={audit.source_provider_mode}
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
            findings={audit.findings || []}
            selectedFindingId={selectedFindingId}
            onSelectFinding={(fId) => setSelectedFindingId(fId)}
          />
        </section>

        {/* Prioritized Corrective Action Plan (WP10) */}
        <FixPlanSection
          auditId={audit.id}
          onSelectFinding={handleSelectFinding}
        />

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
                {(['all', 'pass', 'fail', 'unsure', 'needs_review'] as const).map((st) => (
                  <button
                    key={st}
                    onClick={() => setStatusFilter(st)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors flex items-center gap-1.5 ${
                      statusFilter === st
                        ? 'bg-[var(--color-accent)] text-white'
                        : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] border border-[var(--color-border)]'
                    }`}
                  >
                    <span>
                      {st === 'all'
                        ? 'All'
                        : st === 'pass'
                        ? 'Pass'
                        : st === 'fail'
                        ? 'Fail'
                        : st === 'unsure'
                        ? 'Unsure'
                        : 'Needs Review'}
                    </span>
                    {st === 'needs_review' && needsReviewCount > 0 && (
                      <span className="rounded-full bg-amber-500/20 px-1.5 py-0.2 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                        {needsReviewCount}
                      </span>
                    )}
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
                <div key={f.id} className="space-y-3">
                  <FindingCard
                    finding={f}
                    isSelected={f.id === selectedFindingId}
                    onSelect={() => handleSelectFinding(f.id)}
                    onToggleReview={isReadOnly ? undefined : () =>
                      setReviewingFindingId(reviewingFindingId === f.id ? null : f.id)
                    }
                    isReviewOpen={!isReadOnly && reviewingFindingId === f.id}
                  />

                  {!isReadOnly && reviewingFindingId === f.id && (
                    <div className="pl-4 border-l-2 border-[var(--color-accent)] animate-in fade-in duration-200">
                      <ReviewQueuePanel
                        auditId={audit.id}
                        finding={f}
                        auditLogs={auditLogs}
                        onReviewSuccess={(res, summary, logEntry) => {
                          handleReviewSuccess(f.id, res, summary, logEntry);
                        }}
                      />
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </section>

        {/* Evidence Viewer Interactive Modal (WP8) */}
        <EvidenceViewerModal
          finding={selectedFinding}
          isOpen={isEvidenceModalOpen}
          onClose={() => setIsEvidenceModalOpen(false)}
          onNavigateNext={handleNavigateNext}
          onNavigatePrev={handleNavigatePrev}
          onSeekVideo={(ts) => {
            const videoElem = document.querySelector('video') as HTMLVideoElement | null;
            if (videoElem) {
              videoElem.currentTime = ts;
              videoElem.play().catch(() => {});
            }
          }}
        />

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
