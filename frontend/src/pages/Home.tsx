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
  CheckCircle2,
  Ruler,
  Flame,
  Mic,
  Maximize2,
  Camera,
  Layers,
  ChevronRight,
  AlertTriangle,
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
    navigate(`/new/custom?rule=${encodeURIComponent(customRuleText.trim())}`);
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text)] selection:bg-blue-500/30">
      {/* Provider Mode Alert Banner */}
      {health?.provider_mode === 'mock' && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 text-center text-xs font-medium text-amber-300">
          <span>⚠️ <strong>Mock Mode:</strong> Simulated Detections active. Foundation models (SAM 3.1, Muse Spark, Muse Voice Transcribe) run against deterministic scenarios. All findings stamped MOCK.</span>
        </div>
      )}
      {health?.demo_replay && health?.provider_mode !== 'mock' && (
        <div className="bg-purple-500/10 border-b border-purple-500/20 px-4 py-2 text-center text-xs font-medium text-purple-300">
          <span>📼 <strong>Replay Mode:</strong> Serving exclusively from recorded fixtures in data/fixtures/ with zero network calls. Audit is a replayed run.</span>
        </div>
      )}
      {!health?.demo_replay && health?.provider_mode === 'record' && (
        <div className="bg-emerald-500/10 border-b border-emerald-500/20 px-4 py-2 text-center text-xs font-medium text-emerald-300">
          <span>⏺️ <strong>Record Mode:</strong> Saving live model responses to data/fixtures/ for deterministic replay. Live external AI provider active.</span>
        </div>
      )}
      {health?.provider_mode === 'meta' && (
        <div className="bg-blue-500/10 border-b border-blue-500/20 px-4 py-2 text-center text-xs font-medium text-blue-300">
          <span>🔴 <strong>LIVE Mode:</strong> External Meta Foundation Model API active. SAM 3.1 segmentation, Muse Spark reasoning, Muse Voice Transcribe processing live walkthrough.</span>
        </div>
      )}

      {/* In-page Error Banner */}
      {demoError && (
        <div role="alert" className="bg-rose-950/50 border-b border-rose-900 px-6 py-3 text-xs text-rose-200">
          <div className="mx-auto flex max-w-5xl flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <AlertCircle className="h-4 w-4 text-rose-400 shrink-0" />
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
                className="rounded-md border border-rose-800 px-2.5 py-1 text-rose-300 hover:bg-rose-900/40 transition-colors"
              >
                Dismiss / Home
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Top Navigation */}
      <header className="border-b border-slate-800/80 bg-[var(--color-bg)]/90 backdrop-blur px-4 sm:px-6 py-3.5 sticky top-0 z-30">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 text-white shadow-lg shadow-blue-500/20 ring-1 ring-white/20">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl font-extrabold tracking-tight text-white">
                  AuditLens
                </span>
                <span className="inline-flex items-center rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-mono font-semibold text-cyan-400 border border-cyan-500/20">
                  AI CV 3.1
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium">Evidence-First Safety Pre-Audit Platform</p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
            <Link
              to="/sites"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/80 hover:bg-slate-800/80 px-3 py-1.5 text-xs font-medium text-slate-200 shadow-sm transition-colors min-h-[36px]"
            >
              <Building2 className="h-4 w-4 text-cyan-400" />
              <span className="hidden sm:inline">Sites & History</span>
            </Link>

            <Link
              to="/eval"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/80 hover:bg-slate-800/80 px-3 py-1.5 text-xs font-medium text-slate-200 shadow-sm transition-colors min-h-[36px]"
            >
              <BarChart3 className="h-4 w-4 text-blue-400" />
              <span className="hidden sm:inline">Eval & Calibration</span>
            </Link>

            {health && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-950/60 border border-blue-500/20 px-2.5 sm:px-3 py-1 text-xs font-mono font-medium text-blue-300">
                <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
                {health.provider_mode} mode
              </span>
            )}

            <button
              onClick={() => handleLoadDemo(true)}
              disabled={isStartingDemo}
              className="inline-flex items-center gap-1.5 sm:gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 px-3 sm:px-4 py-1.5 text-xs font-semibold text-white shadow-md shadow-blue-600/25 transition-all min-h-[36px] cursor-pointer"
            >
              {isStartingDemo ? (
                <Loader2 className="h-4 w-4 animate-spin text-white" />
              ) : (
                <PlayCircle className="h-4 w-4 text-white" />
              )}
              <span>Load Demo</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-6xl px-4 sm:px-6 py-8 sm:py-12 space-y-12">
        {/* Hero Section */}
        <section className="text-center space-y-4 pt-2 sm:pt-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/20 bg-blue-950/40 px-3.5 py-1 text-xs font-semibold text-blue-300 shadow-sm">
            <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
            Meta Global AI Hackathon 2026 • Evidence-First Safety Intelligence
          </div>

          <h1 className="text-3xl sm:text-6xl font-black tracking-tight text-white leading-tight">
            Walk through. Get proof. <br className="hidden sm:inline" />
            <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-cyan-400 bg-clip-text text-transparent">
              Fix what matters.
            </span>
          </h1>

          <p className="mx-auto max-w-2xl text-sm sm:text-base text-slate-300 leading-relaxed font-normal">
            Upload phone walkthrough video or keyframe photos across your rooms, workshops, or corridors.
            AuditLens delivers an auditable pre-inspection report powered by Meta SAM 3.1 segmentation, physical geometry depth scaling, and Muse Spark reasoning.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <button
              onClick={() => handleLoadDemo(true)}
              disabled={isStartingDemo}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-blue-500/25 transition-all min-h-[46px] cursor-pointer"
            >
              {isStartingDemo ? (
                <Loader2 className="h-4 w-4 animate-spin text-white" />
              ) : (
                <PlayCircle className="h-4 w-4 text-white" />
              )}
              <span>Launch Guided Demo</span>
              <ArrowRight className="h-4 w-4 text-cyan-200" />
            </button>

            <a
              href="#templates-section"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900/80 hover:bg-slate-800 px-5 py-3 text-sm font-semibold text-slate-200 transition-colors min-h-[46px]"
            >
              <FileCheck className="h-4 w-4 text-cyan-400" />
              <span>Choose Inspection Checklist</span>
            </a>
          </div>
        </section>

        {/* Live Vision Preview Frame (Inspired by reference CV operations platform mockup) */}
        <section className="overflow-hidden rounded-2xl border border-blue-500/20 bg-slate-950/90 shadow-2xl shadow-blue-950/40">
          {/* Top CV Monitor Status Header */}
          <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-900/70 px-4 py-2.5 text-xs font-mono">
            <div className="flex items-center gap-2 text-cyan-400">
              <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
              <span className="font-bold tracking-wider uppercase text-[11px]">LIVE MONITORING</span>
              <span className="text-slate-500">•</span>
              <span className="text-slate-400 text-[11px]">AUTONOMOUS DEFICIENCY DETECTION</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded bg-rose-500/20 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold text-rose-300">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-pulse" />
                LIVE
              </span>
            </div>
          </div>

          {/* Main Inspection Canvas & Side Alerts Area */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-0 border-b border-slate-800/80">
            {/* Visual Viewport (Cols 1-8) */}
            <div className="lg:col-span-8 relative bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 p-4 sm:p-6 min-h-[300px] sm:min-h-[380px] flex flex-col justify-between overflow-hidden">
              {/* Camera Tag & Overlay Controls */}
              <div className="flex items-center justify-between z-10">
                <div className="inline-flex items-center gap-2 rounded-md bg-black/60 backdrop-blur border border-slate-800 px-2.5 py-1 text-xs font-mono text-emerald-400">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  <span>CAM 02 – CORRIDOR WALKTHROUGH</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-400">
                  <button type="button" className="p-1 rounded hover:bg-white/10" aria-label="Camera feed view">
                    <Camera className="h-4 w-4" />
                  </button>
                  <button type="button" className="p-1 rounded hover:bg-white/10" aria-label="Maximize viewport">
                    <Maximize2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Synthetic Visual Stage with Reticles & Detections */}
              <div className="relative my-4 flex-1 flex items-center justify-center">
                {/* Background Walkthrough Corridor Simulation */}
                <div className="absolute inset-0 rounded-xl bg-gradient-to-b from-slate-900/90 via-slate-950/70 to-slate-900/90 border border-slate-800/60 overflow-hidden flex items-center justify-center">
                  {/* Perspective grid lines suggesting a corridor */}
                  <div className="absolute inset-0 opacity-15 bg-[linear-gradient(to_right,#3b82f6_1px,transparent_1px),linear-gradient(to_bottom,#3b82f6_1px,transparent_1px)] bg-[size:3rem_3rem]" />
                  <div className="text-center space-y-1 opacity-25">
                    <Layers className="h-12 w-12 mx-auto text-blue-400" />
                    <p className="text-xs font-mono uppercase tracking-widest text-slate-400">Walkthrough Keyframe Stream</p>
                  </div>
                </div>

                {/* Reticle 1: Detected Extinguisher (Electric Purple / Cyan Accent) */}
                <div className="absolute left-[10%] top-[15%] w-[38%] h-[68%] rounded border border-purple-500/50 bg-purple-500/10 shadow-[0_0_15px_rgba(168,85,247,0.15)] flex flex-col justify-between p-2">
                  <div className="flex items-center justify-between">
                    <div className="inline-flex items-center gap-1.5 rounded-md bg-purple-950/90 border border-purple-400/40 px-2 py-0.5 text-[10px] font-mono font-bold text-purple-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-pulse" />
                      Extinguisher Verified (94%)
                    </div>
                  </div>
                  {/* Reticle Corner Brackets */}
                  <div className="absolute top-0 left-0 w-3 h-3 border-t-2 border-l-2 border-purple-400" />
                  <div className="absolute top-0 right-0 w-3 h-3 border-t-2 border-r-2 border-purple-400" />
                  <div className="absolute bottom-0 left-0 w-3 h-3 border-b-2 border-l-2 border-purple-400" />
                  <div className="absolute bottom-0 right-0 w-3 h-3 border-b-2 border-r-2 border-purple-400" />
                  <span className="text-[10px] font-mono text-purple-300/80 self-end">SAM 3.1 Mask [124×310]</span>
                </div>

                {/* Reticle 2: Corridor Egress Breach (Coral Red Warning) */}
                <div className="absolute right-[12%] bottom-[12%] w-[42%] h-[55%] rounded border border-rose-500/60 bg-rose-500/15 shadow-[0_0_20px_rgba(244,63,94,0.2)] flex flex-col justify-between p-2">
                  <div className="flex items-center justify-between">
                    <div className="inline-flex items-center gap-1.5 rounded-md bg-rose-950/90 border border-rose-400/50 px-2 py-0.5 text-[10px] font-mono font-bold text-rose-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-ping" />
                      Egress Breach: 0.64m &lt; 0.91m
                    </div>
                  </div>
                  {/* Reticle Corner Brackets */}
                  <div className="absolute top-0 left-0 w-3 h-3 border-t-2 border-l-2 border-rose-400" />
                  <div className="absolute top-0 right-0 w-3 h-3 border-t-2 border-r-2 border-rose-400" />
                  <div className="absolute bottom-0 left-0 w-3 h-3 border-b-2 border-l-2 border-rose-400" />
                  <div className="absolute bottom-0 right-0 w-3 h-3 border-b-2 border-r-2 border-rose-400" />
                  <span className="text-[10px] font-mono text-rose-300/90 self-end">Deficiency: Obstruction</span>
                </div>
              </div>

              {/* Viewport Footer Status */}
              <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 pt-2 z-10">
                <span className="text-cyan-400">Resolution: 1920×1080 @ 30fps</span>
                <span>Spatial Calibrated: 1 px ≈ 0.82 mm</span>
              </div>
            </div>

            {/* Live Alerts Feed (Cols 9-12) */}
            <div className="lg:col-span-4 bg-slate-900/60 p-4 sm:p-5 flex flex-col justify-between border-t lg:border-t-0 lg:border-l border-slate-800">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                    Live Incident Feed
                  </span>
                  <button
                    type="button"
                    onClick={() => handleLoadDemo(true)}
                    className="text-[11px] text-cyan-400 hover:text-cyan-300 font-medium cursor-pointer"
                  >
                    View All &rarr;
                  </button>
                </div>

                <div className="space-y-2.5">
                  <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 space-y-1">
                    <div className="flex items-center justify-between text-rose-300 text-xs font-bold">
                      <span className="flex items-center gap-1.5">
                        <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
                        Obstruction Detected
                      </span>
                      <span className="text-[10px] font-mono text-rose-400">10:24:32</span>
                    </div>
                    <p className="text-[11px] text-slate-300 leading-tight">
                      Corridor Aisle 3 clear egress reduced to 0.64m by stacked boxes.
                    </p>
                  </div>

                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-1">
                    <div className="flex items-center justify-between text-amber-300 text-xs font-bold">
                      <span className="flex items-center gap-1.5">
                        <Flame className="h-3.5 w-3.5 text-amber-400" />
                        Access Zone Check
                      </span>
                      <span className="text-[10px] font-mono text-amber-400">10:24:28</span>
                    </div>
                    <p className="text-[11px] text-slate-300 leading-tight">
                      Extinguisher mount clear cone requires 36in unobstructed radius.
                    </p>
                  </div>

                  <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 space-y-1">
                    <div className="flex items-center justify-between text-emerald-300 text-xs font-bold">
                      <span className="flex items-center gap-1.5">
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                        Exit Sign Illuminated
                      </span>
                      <span className="text-[10px] font-mono text-emerald-400">10:23:58</span>
                    </div>
                    <p className="text-[11px] text-slate-300 leading-tight">
                      Overhead directional exit sign detected and verified readable.
                    </p>
                  </div>

                  <div className="rounded-xl border border-blue-500/30 bg-blue-500/10 p-3 space-y-1">
                    <div className="flex items-center justify-between text-blue-300 text-xs font-bold">
                      <span className="flex items-center gap-1.5">
                        <Mic className="h-3.5 w-3.5 text-cyan-400" />
                        Audio Note Correlated
                      </span>
                      <span className="text-[10px] font-mono text-cyan-400">10:23:41</span>
                    </div>
                    <p className="text-[11px] text-slate-300 leading-tight">
                      Auditor verbal note mapped to Keyframe #04 timestamp.
                    </p>
                  </div>
                </div>
              </div>

              <div className="pt-3">
                <button
                  onClick={() => handleLoadDemo(true)}
                  disabled={isStartingDemo}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 py-2 px-3 text-xs font-semibold text-slate-200 transition-colors cursor-pointer"
                >
                  <span>Explore Demo Walkthrough Report</span>
                  <ChevronRight className="h-4 w-4 text-cyan-400" />
                </button>
              </div>
            </div>
          </div>

          {/* Bottom Insights & Gauge Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-4 p-4 sm:p-5 bg-slate-950">
            {/* Insights Cards (Cols 1-8) */}
            <div className="lg:col-span-8 grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">Keyframes</span>
                <span className="text-xl font-bold font-mono text-white">24</span>
                <span className="text-[11px] text-slate-400 block truncate">Frames Analyzed</span>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-rose-400 block">Deficiencies</span>
                <span className="text-xl font-bold font-mono text-rose-400">03</span>
                <span className="text-[11px] text-slate-400 block truncate">Action Required</span>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 block">Passed Rules</span>
                <span className="text-xl font-bold font-mono text-emerald-400">08</span>
                <span className="text-[11px] text-slate-400 block truncate">Compliant</span>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-cyan-400 block">Voice Notes</span>
                <span className="text-xl font-bold font-mono text-cyan-400">02</span>
                <span className="text-[11px] text-slate-400 block truncate">Transcribed</span>
              </div>
            </div>

            {/* Circular Gauge / AI Detection Status (Cols 9-12) */}
            <div className="lg:col-span-4 rounded-xl border border-slate-800 bg-slate-900/60 p-3 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="relative flex h-14 w-14 shrink-0 items-center justify-center">
                  <svg className="h-14 w-14 -rotate-90 transform" viewBox="0 0 36 36">
                    <path
                      className="text-slate-800"
                      strokeWidth="3.5"
                      stroke="currentColor"
                      fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                    <path
                      className="text-cyan-400 transition-all duration-1000 ease-out"
                      strokeDasharray="94, 100"
                      strokeLinecap="round"
                      strokeWidth="3.5"
                      stroke="currentColor"
                      fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                  </svg>
                  <span className="absolute font-mono text-xs font-extrabold text-white">94%</span>
                </div>
                <div>
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider font-mono">Detection Confidence</h4>
                  <div className="flex items-center gap-2 pt-0.5 text-[11px] text-slate-400">
                    <span className="flex items-center gap-1 text-emerald-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      SAM 3.1 Active
                    </span>
                    <span className="flex items-center gap-1 text-cyan-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
                      Muse Spark
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 5-Step Process Strip for Judges */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 font-mono">
              The 5-Stage Verification Pipeline
            </h2>
            <span className="text-xs text-slate-500 font-mono">Autonomous • Auditable • Deterministic</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-left">
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 space-y-1.5 shadow-sm">
              <div className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-500/20 text-cyan-400 text-[11px] font-bold font-mono">01</span>
                <span className="text-xs font-bold text-white truncate">Walkthrough</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">
                Phone video or keyframe photos captured at standard walking pace.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 space-y-1.5 shadow-sm">
              <div className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-400 text-[11px] font-bold font-mono">02</span>
                <span className="text-xs font-bold text-white truncate">SAM 3.1 Vision</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">
                Sub-pixel polygon segmentation with strict confidence floors.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 space-y-1.5 shadow-sm">
              <div className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-purple-500/20 text-purple-400 text-[11px] font-bold font-mono">03</span>
                <span className="text-xs font-bold text-white truncate">Geometry & Code</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">
                Optical clear width depth scaling and clearance calculations.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 space-y-1.5 shadow-sm">
              <div className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-cyan-500/20 text-cyan-400 text-[11px] font-bold font-mono">04</span>
                <span className="text-xs font-bold text-white truncate">Muse Spark Reasoning</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">
                Evaluates evidence against requirements and authors prioritized fix plans.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3.5 space-y-1.5 shadow-sm col-span-2 sm:col-span-1">
              <div className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 text-[11px] font-bold font-mono">05</span>
                <span className="text-xs font-bold text-white truncate">Re-Audit Compare</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">
                Differential proof certifying resolved versus persistent hazards.
              </p>
            </div>
          </div>
        </section>

        {/* Disclaimer Banner */}
        <Disclaimer compact />

        {/* Supported Capabilities Grid (What the AI checks) */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-400" />
              <span>What AuditLens Inspects (Evidence-Backed Rules)</span>
            </h2>
            <span className="text-xs text-slate-400 hidden sm:inline font-mono">
              Evidence-first • No hallucinated findings
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-2 shadow-sm">
              <div className="flex items-center gap-2 text-cyan-400">
                <Ruler className="h-4 w-4" />
                <h4 className="text-xs font-bold text-white">Clear Egress Width</h4>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Measures passage clearance against physical thresholds (≥ 36 in / 0.91 m) using optical depth scaling and corridor boundary planes.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-2 shadow-sm">
              <div className="flex items-center gap-2 text-rose-400">
                <Flame className="h-4 w-4" />
                <h4 className="text-xs font-bold text-white">Fire Extinguisher Access</h4>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                SAM 3.1 segmenter detects wall-mounted extinguishers, verifies unobstructed access cones, and checks proximity signage.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-2 shadow-sm">
              <div className="flex items-center gap-2 text-emerald-400">
                <Shield className="h-4 w-4" />
                <h4 className="text-xs font-bold text-white">Exit Signage & Doors</h4>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Verifies visible illuminated emergency exit signs along paths and checks that panic hardware and emergency doors are not padlocked.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-2 shadow-sm">
              <div className="flex items-center gap-2 text-indigo-400">
                <Mic className="h-4 w-4" />
                <h4 className="text-xs font-bold text-white">Voice Note Mapping</h4>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Muse Voice Transcribe captures spoken walkthrough notes and automatically correlates reported hazards to keyframe visual locations.
              </p>
            </div>
          </div>
        </section>

        {/* Template Checklists */}
        <section id="templates-section" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white">
              Choose an Inspection Checklist
            </h2>
            <span className="text-xs text-slate-400 font-mono">
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
        <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-6 shadow-sm space-y-3">
          <div className="flex items-center gap-2">
            <FileCheck className="h-5 w-5 text-cyan-400" />
            <h2 className="text-lg font-bold text-white">
              Or Write Your Own Custom Safety Rule
            </h2>
          </div>
          <p className="text-xs text-slate-400">
            Type any plain-language inspection requirement. AuditLens compiles it into deterministic absence, presence, or count checks.
          </p>
          <form onSubmit={handleStartCustomRule} className="flex flex-col sm:flex-row gap-2.5 pt-1">
            <input
              type="text"
              value={customRuleText}
              onChange={(e) => setCustomRuleText(e.target.value)}
              placeholder="e.g. 'No cardboard boxes blocking the emergency electrical panel'"
              className="flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              disabled={!customRuleText.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors disabled:opacity-50 cursor-pointer"
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
              <History className="h-5 w-5 text-slate-400" />
              <h2 className="text-xl font-bold text-white">
                Recent Audits
              </h2>
            </div>
            {recentAudits.length > 0 && (
              <Link to="/compare" className="text-xs font-semibold text-cyan-400 hover:underline">
                Compare Audits &rarr;
              </Link>
            )}
          </div>

          {recentAudits.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-800 p-8 text-center space-y-2">
              <Clock className="mx-auto h-8 w-8 text-slate-500 opacity-60" />
              <p className="text-sm font-medium text-slate-300">
                No audits conducted yet
              </p>
              <p className="text-xs text-slate-400">
                Click "Load Demo Audit" above to test with pre-generated walkthrough video in 1 click.
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/80 divide-y divide-slate-800">
              {recentAudits.map((a) => {
                const summary = a.summary;
                const score = summary?.score ?? 0;
                const grade = getScoreGrade(score);

                return (
                  <div
                    key={a.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 hover:bg-slate-800/50 transition-colors"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2.5">
                        <span className="font-semibold text-sm text-white">
                          {a.template_id.replace(/_/g, ' ').toUpperCase()}
                        </span>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-mono font-medium ${
                          a.status === 'completed' ? 'bg-emerald-950 border border-emerald-500/30 text-emerald-300' :
                          a.status === 'processing' ? 'bg-blue-950 border border-blue-500/30 text-blue-300 animate-pulse' :
                          a.status === 'failed' ? 'bg-rose-950 border border-rose-500/30 text-rose-300' :
                          'bg-slate-800 text-slate-300'
                        }`}>
                          {a.status}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 font-mono">
                        ID: {a.id} · {new Date(a.created_at).toLocaleString()}
                      </p>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end gap-5">
                      {summary && (
                        <div className="text-right">
                          <span className={`text-lg font-bold font-mono ${grade.colorClass}`}>
                            {score}
                            <span className="text-xs font-normal text-slate-400">/100</span>
                          </span>
                          <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400">
                            <span className="text-emerald-400">✓ {summary.pass}</span>
                            <span className="text-rose-400">✗ {summary.fail}</span>
                            <span className="text-amber-400">? {summary.unsure}</span>
                          </div>
                        </div>
                      )}

                      <Link
                        to={a.status === 'completed' ? `/audits/${a.id}` : `/audits/${a.id}/processing`}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 transition-colors"
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
