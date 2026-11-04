import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Shield,
  Upload,
  ArrowRight,
  Sparkles,
  PlayCircle,
  Clock,
  History,
  FileCheck,
  Loader2,
  BarChart3,
  Building2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import {
  getAudits,
  getHealth,
  getTemplates,
  createDemoAudit,
  type HealthResponse,
} from '../api/client';
import type { Audit, Template } from '../api/types';
import TemplateCard from '../components/TemplateCard';
import Disclaimer from '../components/Disclaimer';
import { getScoreGrade } from '../utils/formatters';

export default function Home() {
  const navigate = useNavigate();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [recentAudits, setRecentAudits] = useState<Audit[]>([]);
  const [customRuleText, setCustomRuleText] = useState('');
  const [isStartingDemo, setIsStartingDemo] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [lastReplayMode, setLastReplayMode] = useState<boolean>(false);

  useEffect(() => {
    getHealth().then(setHealth).catch(console.error);
    getTemplates()
      .then((tmpls) => {
        const sorted = [...tmpls].sort((a, b) => (a.id === 'campus_fire_exit_core' ? -1 : b.id === 'campus_fire_exit_core' ? 1 : 0));
        setTemplates(sorted);
      })
      .catch(console.error);
    getAudits().then(setRecentAudits).catch(console.error);
  }, []);

  async function handleLoadDemo(replay: boolean = false) {
    try {
      setDemoError(null);
      setLastReplayMode(replay);
      setIsStartingDemo(true);
      const res = await createDemoAudit('campus_fire_exit_core', replay);
      navigate(`/audits/${res.id}/processing`);
    } catch (err: any) {
      setDemoError(err.message || 'Could not start demo audit');
    } finally {
      setIsStartingDemo(false);
    }
  }

  async function handleStartCustomRule(e: React.FormEvent) {
    e.preventDefault();
    if (!customRuleText.trim()) return;
    // Navigate to capture with custom rule pre-filled
    navigate(`/new/custom?rule=${encodeURIComponent(customRuleText.trim())}`);
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* Provider Mode Alert Banner */}
      {health?.provider_mode === 'mock' && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 text-center text-xs font-medium text-amber-800 dark:text-amber-200">
          <span>⚠️ <strong>Mock Mode:</strong> Simulated Detections active. Foundation models (SAM 3.1, Muse Spark, Muse Voice Transcribe) run against deterministic scenarios. All findings stamped MOCK.</span>
        </div>
      )}
      {health?.demo_replay && health?.provider_mode !== 'mock' && (
        <div className="bg-purple-500/10 border-b border-purple-500/20 px-4 py-2 text-center text-xs font-medium text-purple-800 dark:text-purple-200">
          <span>📼 <strong>Replay Mode:</strong> Serving exclusively from recorded fixtures in data/fixtures/ with zero network calls. Audit is a replayed run.</span>
        </div>
      )}
      {!health?.demo_replay && health?.provider_mode === 'record' && (
        <div className="bg-emerald-500/10 border-b border-emerald-500/20 px-4 py-2 text-center text-xs font-medium text-emerald-800 dark:text-emerald-200">
          <span>⏺️ <strong>Record Mode:</strong> Saving live model responses to data/fixtures/ for deterministic replay. Live external AI provider active.</span>
        </div>
      )}
      {health?.provider_mode === 'meta' && (
        <div className="bg-blue-500/10 border-b border-blue-500/20 px-4 py-2 text-center text-xs font-medium text-blue-800 dark:text-blue-200">
          <span>🔴 <strong>LIVE Mode:</strong> External Meta Foundation Model API active. SAM 3.1 segmentation, Muse Spark reasoning, Muse Voice Transcribe processing live walkthrough.</span>
        </div>
      )}

      {/* In-page Error Banner */}
      {demoError && (
        <div role="alert" className="bg-rose-50 border-b border-rose-200 px-6 py-3 text-xs text-rose-800 dark:bg-rose-950/40 dark:border-rose-900 dark:text-rose-200">
          <div className="mx-auto flex max-w-5xl flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
              <div>
                <span className="font-bold mr-1.5">Could not start demo audit:</span>
                <span className="font-mono text-[11px]">{demoError}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => handleLoadDemo(lastReplayMode)}
                className="inline-flex items-center gap-1 rounded-md bg-rose-600 px-3 py-1 font-semibold text-white shadow-sm hover:bg-rose-700 transition-colors"
              >
                <RefreshCw className="h-3 w-3" />
                Retry
              </button>
              <Link
                to="/"
                onClick={() => setDemoError(null)}
                className="rounded-md border border-rose-300 dark:border-rose-800 px-2.5 py-1 text-rose-700 dark:text-rose-300 hover:bg-rose-100 dark:hover:bg-rose-900/40 transition-colors"
              >
                Dismiss / Home
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Top Navigation */}
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]/80 backdrop-blur px-6 py-4 sticky top-0 z-20">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-accent)] text-white shadow-sm">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <span className="text-xl font-bold tracking-tight text-[var(--color-text)]">
                AuditLens
              </span>
              <span className="hidden sm:inline-block ml-2 text-xs font-mono text-[var(--color-text-secondary)]">
                v0.2
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/sites"
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] shadow-sm hover:bg-[var(--color-bg-secondary)]"
            >
              <Building2 className="h-4 w-4 text-indigo-500" />
              <span className="hidden sm:inline">Sites & History</span>
            </Link>

            <Link
              to="/eval"
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] shadow-sm hover:bg-[var(--color-bg-secondary)]"
            >
              <BarChart3 className="h-4 w-4 text-blue-500" />
              <span className="hidden sm:inline">Eval & Calibration</span>
            </Link>

            {health && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 ring-1 ring-blue-700/10 dark:bg-blue-950/60 dark:text-blue-300">
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                {health.provider_mode} mode
              </span>
            )}

            <button
              onClick={() => handleLoadDemo(false)}
              disabled={isStartingDemo}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-1.5 text-xs font-medium text-[var(--color-text)] shadow-sm hover:bg-[var(--color-bg-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            >
              {isStartingDemo ? (
                <Loader2 className="h-4 w-4 animate-spin text-[var(--color-accent)]" />
              ) : (
                <PlayCircle className="h-4 w-4 text-[var(--color-accent)]" />
              )}
              <span>Load Demo Audit <strong className="text-[10px] text-amber-600 dark:text-amber-400 font-mono">(Demo Data)</strong></span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-5xl px-4 sm:px-6 py-8 sm:py-10 space-y-10 sm:space-y-12">
        {/* Hero */}
        <section className="text-center space-y-4 pt-2 sm:pt-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50/80 px-3.5 py-1 text-xs font-semibold text-blue-800 dark:border-blue-900 dark:bg-blue-950/50 dark:text-blue-200 shadow-sm">
            <Sparkles className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
            Evidence-First Safety Pre-Audit Platform
          </div>
          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-[var(--color-text)] leading-tight">
            Walk through. Get proof. <br className="hidden sm:inline" />
            <span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              Fix what matters.
            </span>
          </h1>
          <p className="mx-auto max-w-2xl text-sm sm:text-base text-[var(--color-text-secondary)] leading-relaxed">
            Upload phone walkthrough video or photos of your room, workshop, or corridor.
            AuditLens delivers an evidence-backed pre-inspection report with pixel-level segmentation masks, optical measurements, and plain-language corrective fixes.
          </p>

          {/* 3-Step Process Strip for Judges */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 max-w-3xl mx-auto text-left">
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 shadow-sm">
              <div className="flex items-center gap-2 mb-1">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300 text-xs font-bold font-mono">1</span>
                <span className="text-xs font-bold text-[var(--color-text)]">Walkthrough Capture</span>
              </div>
              <p className="text-[11px] text-[var(--color-text-secondary)] leading-normal">
                Standard smartphone video or photo keyframes (up to 90s, no special hardware).
              </p>
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 shadow-sm">
              <div className="flex items-center gap-2 mb-1">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 text-xs font-bold font-mono">2</span>
                <span className="text-xs font-bold text-[var(--color-text)]">Foundation Vision</span>
              </div>
              <p className="text-[11px] text-[var(--color-text-secondary)] leading-normal">
                SAM 3.1 mask segmentation + Muse Spark tool-calling agent with strict confidence floors.
              </p>
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 shadow-sm">
              <div className="flex items-center gap-2 mb-1">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 text-xs font-bold font-mono">3</span>
                <span className="text-xs font-bold text-[var(--color-text)]">Verified Report & Fixes</span>
              </div>
              <p className="text-[11px] text-[var(--color-text-secondary)] leading-normal">
                Pass/Fail pre-audit score, bounding-box overlays, optical scale and corrective fix plan.
              </p>
            </div>
          </div>
        </section>

        {/* Disclaimer Banner */}
        <Disclaimer compact />

        {/* Guided Demo Walkthrough Card (Judge Priority) */}
        <section className="relative overflow-hidden rounded-2xl border-2 border-indigo-300 dark:border-indigo-800 bg-gradient-to-br from-indigo-50/90 via-blue-50/60 to-purple-50/50 dark:from-indigo-950/40 dark:via-blue-950/30 dark:to-purple-950/30 p-5 sm:p-6 shadow-md">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-5">
            <div className="space-y-2 max-w-xl">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-white shadow-sm">
                  ⚡ JUDGE QUICKSTART
                </span>
                <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-[11px] font-bold text-amber-800 dark:text-amber-300 border border-amber-500/30">
                  Recorded Run / MOCK
                </span>
              </div>
              <h3 className="font-bold text-base sm:text-lg text-[var(--color-text)]">
                Launch Interactive Guided Demo Walkthrough
              </h3>
              <p className="text-xs sm:text-sm text-[var(--color-text-secondary)] leading-relaxed">
                Experience the full end-to-end pipeline in seconds with zero upload needed. Replays an authentic campus safety inspection walkthrough with real-time agent event streaming, interactive video timeline, mask-backed detections, and automated fix recommendations.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 shrink-0">
              <button
                onClick={() => handleLoadDemo(true)}
                disabled={isStartingDemo}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 px-5 py-3 text-xs sm:text-sm font-bold text-white shadow-md hover:shadow-lg disabled:opacity-50 transition-all cursor-pointer min-h-[44px]"
              >
                {isStartingDemo ? (
                  <Loader2 className="h-4 w-4 animate-spin text-white" />
                ) : (
                  <PlayCircle className="h-4 w-4 text-white" />
                )}
                <span>Launch Guided Demo</span>
                <ArrowRight className="h-3.5 w-3.5 text-indigo-200" />
              </button>
            </div>
          </div>
        </section>

        {/* Template Checklists */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-[var(--color-text)]">
              Choose an Inspection Checklist
            </h2>
            <span className="text-xs text-[var(--color-text-secondary)]">
              {templates.length} verified templates available
            </span>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            {templates.map((tmpl) => (
              <TemplateCard key={tmpl.id} template={tmpl} />
            ))}
          </div>
        </section>

        {/* Custom Rule Box */}
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-sm space-y-3">
          <div className="flex items-center gap-2">
            <FileCheck className="h-5 w-5 text-[var(--color-accent)]" />
            <h2 className="text-lg font-bold text-[var(--color-text)]">
              Or Write Your Own Custom Safety Rule
            </h2>
          </div>
          <p className="text-xs text-[var(--color-text-secondary)]">
            Type any plain-language inspection requirement. AuditLens compiles it into deterministic absence, presence, or count checks.
          </p>
          <form onSubmit={handleStartCustomRule} className="flex flex-col sm:flex-row gap-2.5 pt-1">
            <input
              type="text"
              value={customRuleText}
              onChange={(e) => setCustomRuleText(e.target.value)}
              placeholder="e.g. 'No cardboard boxes blocking the emergency electrical panel'"
              className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-2.5 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            />
            <button
              type="submit"
              disabled={!customRuleText.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--color-accent)] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
            >
              <Upload className="h-4 w-4" />
              <span>Start Custom Audit</span>
            </button>
          </form>
        </section>

        {/* Recent Audits */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-[var(--color-text-secondary)]" />
              <h2 className="text-xl font-bold text-[var(--color-text)]">
                Recent Audits
              </h2>
            </div>
            {recentAudits.length > 0 && (
              <Link to="/compare" className="text-xs font-medium text-[var(--color-accent)] hover:underline">
                Compare Audits &rarr;
              </Link>
            )}
          </div>

          {recentAudits.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--color-border)] p-8 text-center space-y-2">
              <Clock className="mx-auto h-8 w-8 text-[var(--color-text-secondary)] opacity-60" />
              <p className="text-sm font-medium text-[var(--color-text)]">
                No audits conducted yet
              </p>
              <p className="text-xs text-[var(--color-text-secondary)]">
                Click "Load Demo Audit" above to test with pre-generated walkthrough video in 1 click.
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] divide-y divide-[var(--color-border)]">
              {recentAudits.map((a) => {
                const summary = a.summary;
                const score = summary?.score ?? 0;
                const grade = getScoreGrade(score);

                return (
                  <div
                    key={a.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 hover:bg-[var(--color-bg-secondary)] transition-colors"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2.5">
                        <span className="font-semibold text-sm text-[var(--color-text)]">
                          {a.template_id.replace(/_/g, ' ').toUpperCase()}
                        </span>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-mono font-medium ${
                          a.status === 'completed' ? 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300' :
                          a.status === 'processing' ? 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300 animate-pulse' :
                          a.status === 'failed' ? 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300' :
                          'bg-slate-100 text-slate-800'
                        }`}>
                          {a.status}
                        </span>
                      </div>
                      <p className="text-xs text-[var(--color-text-secondary)] font-mono">
                        ID: {a.id} · {new Date(a.created_at).toLocaleString()}
                      </p>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end gap-5">
                      {summary && (
                        <div className="text-right">
                          <span className={`text-lg font-bold font-mono ${grade.colorClass}`}>
                            {score}
                            <span className="text-xs font-normal text-[var(--color-text-secondary)]">/100</span>
                          </span>
                          <div className="flex items-center gap-2 text-[11px] font-mono text-[var(--color-text-secondary)]">
                            <span className="text-green-600">✓ {summary.pass}</span>
                            <span className="text-red-600">✗ {summary.fail}</span>
                            <span className="text-amber-600">? {summary.unsure}</span>
                          </div>
                        </div>
                      )}

                      <Link
                        to={a.status === 'completed' ? `/audits/${a.id}` : `/audits/${a.id}/processing`}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
                      >
                        {a.status === 'completed' ? 'View Report' : 'Track'}
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
