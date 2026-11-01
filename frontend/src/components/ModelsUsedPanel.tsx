import { Cpu, Zap, Layers } from 'lucide-react';
import type { CostSummary } from '../api/client';

export interface ModelsUsedPanelProps {
  costSummary: CostSummary | null;
  providerMode?: string;
  models?: {
    segmentation?: string;
    agent?: string;
    transcription?: string;
  };
  isReplay?: boolean;
  sourceProviderMode?: string;
}

export default function ModelsUsedPanel({
  costSummary,
  providerMode = 'mock',
  models,
  isReplay = false,
  sourceProviderMode,
}: ModelsUsedPanelProps) {
  const isMock = providerMode.toLowerCase() === 'mock';
  const isLiveReplay = isReplay && sourceProviderMode === 'record';
  const isSimulated = isMock || isReplay || providerMode.toLowerCase() === 'replay' || providerMode.toLowerCase() === 'mock';

  // Fallbacks if costSummary not yet loaded
  const segData = costSummary?.by_provider?.segmentation || {
    name: 'Segmentation',
    model_id: models?.segmentation || 'SAM 3.1',
    role: `${models?.segmentation || 'SAM 3.1'}: finds and measures items`,
    calls: 0,
    cache_hits: 0,
    latency_ms: 0,
    units: 0,
    cost_usd: 0,
    simulated: isMock,
  };

  const agentData = costSummary?.by_provider?.agent || {
    name: 'Agent / Reasoning',
    model_id: models?.agent || 'Muse Spark',
    role: `${models?.agent || 'Muse Spark'}: reasons over rules, dispatches tools, and evaluates evidence`,
    calls: 0,
    cache_hits: 0,
    latency_ms: 0,
    units: 0,
    cost_usd: 0,
    simulated: isMock,
  };

  const transData = costSummary?.by_provider?.transcription || {
    name: 'Voice Transcription',
    model_id: models?.transcription || 'Muse Voice Transcribe',
    role: `${models?.transcription || 'Muse Voice Transcribe'}: transcribes audio notes into searchable evidence`,
    calls: 0,
    cache_hits: 0,
    latency_ms: 0,
    units: 0,
    cost_usd: 0,
    simulated: isMock,
  };

  const providers = [
    { key: 'segmentation', label: 'Segmentation', data: segData, icon: Layers },
    { key: 'agent', label: 'Agent Planner', data: agentData, icon: Cpu },
    { key: 'transcription', label: 'Voice Audio', data: transData, icon: Zap },
  ];

  return (
    <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-sm space-y-4 print:border-slate-300 print:bg-white print:p-4 print:my-4 print:break-inside-avoid">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[var(--color-border)] pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
            <Cpu className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-[var(--color-text)] flex items-center gap-2">
              <span>Models Used & Provider Evidence</span>
              {isReplay && (
                <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase text-amber-700 dark:text-amber-400 border border-amber-500/30">
                  {isLiveReplay ? 'RECORDED RUN (live providers)' : 'SIMULATED REPLAY (mock fixtures)'}
                </span>
              )}
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)]">
              Auditable accounting of foundation model invocations, latency, and cache hits.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isMock ? (
            <span className="rounded-md bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-700 dark:text-amber-400 border border-amber-500/20">
              Mock Mode: Simulated Detections
            </span>
          ) : providerMode === 'replay' ? (
            <span className="rounded-md bg-purple-500/10 px-2.5 py-1 text-xs font-semibold text-purple-700 dark:text-purple-400 border border-purple-500/20">
              Replay Mode: Stored Fixtures
            </span>
          ) : providerMode === 'record' ? (
            <span className="rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
              Record Mode: Capturing Fixtures
            </span>
          ) : (
            <span className="rounded-md bg-blue-500/10 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:text-blue-400 border border-blue-500/20">
              Live Meta Models
            </span>
          )}
        </div>
      </div>

      {/* Provider Model Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {providers.map(({ key, label, data, icon: Icon }) => (
          <div
            key={key}
            className="flex flex-col justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-3.5 space-y-3 print:bg-slate-50 print:border-slate-200"
          >
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)] flex items-center gap-1.5">
                  <Icon className="h-3 w-3 text-[var(--color-accent)]" />
                  {label}
                </span>
                {data.simulated && (
                  <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-bold text-amber-600 dark:text-amber-400">
                    Simulated
                  </span>
                )}
              </div>

              <div className="font-mono text-sm font-bold text-[var(--color-text)]">
                {data.model_id || 'Configured Model'}
              </div>

              <p className="text-xs text-[var(--color-text-secondary)] leading-snug">
                {data.role || `${data.model_id}: foundation AI model`}
              </p>
            </div>

            <div className="border-t border-[var(--color-border)] pt-2.5 grid grid-cols-2 gap-2 text-[11px] font-mono">
              <div>
                <span className="text-[var(--color-text-secondary)] block text-[10px]">Calls / Hits</span>
                <span className="font-semibold text-[var(--color-text)]">
                  {data.calls} calls <span className="text-slate-400">({data.cache_hits || 0} hit)</span>
                </span>
              </div>

              <div>
                <span className="text-[var(--color-text-secondary)] block text-[10px]">Total Latency</span>
                <span className="font-semibold text-[var(--color-text)]">
                  {data.latency_ms || 0} ms
                </span>
              </div>

              <div className="col-span-2 flex items-center justify-between pt-1 border-t border-[var(--color-border)]/60">
                <span className="text-[var(--color-text-secondary)] text-[10px]">Est. Cost:</span>
                <span className="font-bold text-green-700 dark:text-green-400">
                  ${(data.cost_usd || 0).toFixed(4)} USD
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Aggregate metrics footer */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pt-1 text-xs text-[var(--color-text-secondary)] font-mono">
        <div className="flex items-center gap-4">
          <span>
            Total Invocations: <strong className="text-[var(--color-text)]">{costSummary?.total_calls || 0}</strong>
          </span>
          <span>
            Total Est. Cost: <strong className="text-green-700 dark:text-green-400">${(costSummary?.total_cost_usd || 0).toFixed(4)} USD</strong>
          </span>
        </div>
        <span className="text-[10px] text-slate-500 italic">
          * Source: cost_log table. {isSimulated ? 'Latencies and costs are simulated.' : 'Latencies and costs measured from local execution.'}
        </span>
      </div>

      {/* Meta Stack Roles Table */}
      <div className="mt-2 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 p-3 text-xs space-y-2">
        <div className="font-semibold text-slate-700 dark:text-slate-300 text-[11px] uppercase tracking-wider">
          Which Meta model does what, and why
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-[11px] text-[var(--color-text-secondary)]">
          <div className="p-2 rounded bg-white dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60">
            <span className="font-bold text-[var(--color-text)] block">SAM 3.1 (sam-3.1)</span>
            <span>Zero-shot object & region segmentation. Outputs tight polygon masks & bboxes for precise clearance measurements.</span>
          </div>
          <div className="p-2 rounded bg-white dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60">
            <span className="font-bold text-[var(--color-text)] block">Muse Spark (muse-spark-1.3)</span>
            <span>Multimodal reasoning agent. Dispatches tool calls, evaluates visual evidence against rules, compiles checklists, and generates fix plans.</span>
          </div>
          <div className="p-2 rounded bg-white dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60">
            <span className="font-bold text-[var(--color-text)] block">Muse Voice (muse-voice-transcribe)</span>
            <span>Walkthrough speech-to-text. Transcribes auditor field notes and associates observations to nearest keyframe timestamps.</span>
          </div>
        </div>
      </div>
    </section>
  );
}
