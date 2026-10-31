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

  useEffect(() => {
    getHealth().then(setHealth).catch(console.error);
    getTemplates().then(setTemplates).catch(console.error);
    getAudits().then(setRecentAudits).catch(console.error);
  }, []);

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
          <span>⚠️ <strong>Mock Mode:</strong> Simulated Detections active. Foundation models (SAM 3.1, Muse Spark, Muse Voice Transcribe) run against deterministic scenarios.</span>
        </div>
      )}
      {health?.provider_mode === 'replay' && (
        <div className="bg-purple-500/10 border-b border-purple-500/20 px-4 py-2 text-center text-xs font-medium text-purple-800 dark:text-purple-200">
          <span>📼 <strong>Replay Mode:</strong> Serving exclusively from recorded fixtures in data/fixtures/ with zero network calls.</span>
        </div>
      )}
      {health?.provider_mode === 'record' && (
        <div className="bg-emerald-500/10 border-b border-emerald-500/20 px-4 py-2 text-center text-xs font-medium text-emerald-800 dark:text-emerald-200">
          <span>⏺️ <strong>Record Mode:</strong> Saving live model responses to data/fixtures/ for deterministic replay.</span>
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
              onClick={handleLoadDemo}
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
      <main className="mx-auto max-w-5xl px-6 py-10 space-y-12">
        {/* Hero */}
        <section className="text-center space-y-3 pt-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50/70 px-3.5 py-1 text-xs font-medium text-blue-800 dark:border-blue-900 dark:bg-blue-950/50 dark:text-blue-200">
            <Sparkles className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
            Assistive Safety Pre-Audit
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-[var(--color-text)]">
            Walk through. Get proof. Fix what matters.
          </h1>
          <p className="mx-auto max-w-2xl text-base sm:text-lg text-[var(--color-text-secondary)]">
            Upload phone walkthrough video of your room, workshop, or lab.
            Receive an evidence-backed report with bounding-box overlays, optical measurements, and plain-language fixes.
          </p>
        </section>

        {/* Disclaimer Banner */}
        <Disclaimer compact />

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
