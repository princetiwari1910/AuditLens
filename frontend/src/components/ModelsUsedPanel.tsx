import { Cpu, Zap, Layers, Sparkles } from 'lucide-react';
import type { CostSummary } from '../api/client';
import ReplayBadge from './ReplayBadge';

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
    {
      key: 'segmentation',
      label: 'Vision & Segmentation',
      data: segData,
      icon: Layers,
      color: 'text-indigo-400',
      badgeBg: 'bg-indigo-500/10 border-indigo-500/20 text-indigo-300',
      description: 'Zero-shot polygon object extraction with pixel-level mask geometry.'
    },
    {
      key: 'agent',
      label: 'Agent & Multimodal Reasoning',
      data: agentData,
      icon: Cpu,
      color: 'text-cyan-400',
      badgeBg: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
      description: 'Multimodal safety reasoning, structured rule checklist dispatch & fix planning.'
    },
    {
      key: 'transcription',
      label: 'Walkthrough Audio Log',
      data: transData,
      icon: Zap,
      color: 'text-purple-400',
      description: transData.calls > 0
        ? 'Speech-to-text turns transcribed and linked to visual evidence.'
        : 'Transcription unavailable — Meta API returned 404.'
    },
  ];

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 sm:p-6 shadow-xl shadow-blue-950/20 space-y-4 print:border-slate-300 print:bg-white print:p-4 print:my-4 print:break-inside-avoid">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-500 text-white shadow-md shadow-blue-600/30">
            <Cpu className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>Models Used & Provider Evidence</span>
              <ReplayBadge
                isReplay={isReplay}
                sourceProviderMode={sourceProviderMode}
                className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase text-amber-300 border border-amber-500/30"
              />
            </h3>
            <p className="text-xs text-slate-400">
              Auditable Meta AI foundation model invocations, latency accounting, and cache efficiency.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isMock ? (
            <span className="rounded-lg bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-300 border border-amber-500/20 font-mono">
              Mock Mode: Simulated Detections
            </span>
          ) : providerMode === 'replay' ? (
            <span className="rounded-lg bg-purple-500/10 px-3 py-1 text-xs font-semibold text-purple-300 border border-purple-500/20 font-mono">
              Replay Mode: Stored Fixtures
            </span>
          ) : providerMode === 'record' ? (
            <span className="rounded-lg bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300 border border-emerald-500/20 font-mono">
              Record Mode: Capturing Fixtures
            </span>
          ) : (
            <span className="rounded-lg bg-blue-500/10 px-3 py-1 text-xs font-semibold text-cyan-300 border border-blue-500/20 font-mono">
              Live Meta Models: SAM 3.1 &amp; Muse Spark
            </span>
          )}
        </div>
      </div>

      {/* Provider Model Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {providers.map(({ key, label, data, icon: Icon, color, description }) => (
          <div
            key={key}
            className="flex flex-col justify-between rounded-xl border border-slate-800/90 bg-slate-950/70 p-4 space-y-3.5 hover:border-slate-700 transition-colors print:bg-slate-50 print:border-slate-200"
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className={`text-[11px] font-bold uppercase tracking-wider ${color} flex items-center gap-1.5 font-mono`}>
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                </span>
                {data.simulated && (
                  <span className="rounded bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 text-[9px] font-bold text-amber-400 font-mono">
                    Simulated
                  </span>
                )}
              </div>

              <div className="font-mono text-base font-extrabold text-white flex items-center gap-2">
                <span>{data.model_id || 'Configured Model'}</span>
              </div>

              <p className="text-xs text-slate-300 leading-snug">
                {data.role || `${data.model_id}: foundation AI model`}
              </p>
              <p className="text-[11px] text-slate-500 leading-tight">
                {description}
              </p>
            </div>

            <div className="border-t border-slate-800/80 pt-3 grid grid-cols-2 gap-2 text-[11px] font-mono">
              <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800/60">
                <span className="text-slate-400 block text-[10px] uppercase">Calls / Hits</span>
                <span className="font-semibold text-white">
                  {data.calls} calls <span className="text-slate-500">({data.cache_hits || 0} hit)</span>
                </span>
              </div>

              <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800/60">
                <span className="text-slate-400 block text-[10px] uppercase">Total Latency</span>
                <span className="font-semibold text-cyan-300">
                  {data.latency_ms || 0} ms
                </span>
              </div>

              <div className="col-span-2 flex items-center justify-between px-2 py-1.5 bg-slate-900/40 rounded border border-slate-800/40">
                <span className="text-slate-400 text-[10px] uppercase">Est. Cost:</span>
                <span className="font-bold text-emerald-400 text-[11px]">
                  ${(data.cost_usd || 0).toFixed(4)} USD <span className="text-slate-500 font-normal">({isSimulated ? 'simulated' : 'placeholder rate'})</span>
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Aggregate metrics footer */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pt-1 text-xs text-slate-400 font-mono border-t border-slate-800/60">
        <div className="flex items-center gap-4">
          <span>
            Total Invocations: <strong className="text-white">{costSummary?.total_calls || 0}</strong>
          </span>
          <span>
            Total Est. Cost: <strong className="text-emerald-400">${(costSummary?.total_cost_usd || 0).toFixed(4)} USD</strong>
          </span>
        </div>
        <span className="text-[10px] text-slate-500 italic">
          * Source: cost_log table. {isSimulated ? 'Latencies and costs are simulated. Costs reflect mock estimates, not actual billing.' : 'Latencies and costs measured from local execution. Costs use UNIT_PRICE_* placeholder rates, not provider billing.'}
        </span>
      </div>

      {/* Meta Stack Roles Table */}
      <div className="mt-2 rounded-xl bg-slate-950/80 border border-slate-800 p-3.5 text-xs space-y-2">
        <div className="font-semibold text-slate-300 text-[11px] uppercase tracking-wider font-mono flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
          Which Meta model does what, and why
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 text-[11px] text-slate-300">
          <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
            <span className="font-bold text-white block font-mono text-xs">SAM 3.1 (sam-3.1)</span>
            <span className="text-slate-400">Zero-shot object & region segmentation. Outputs tight polygon masks & bboxes for precise clearance measurements.</span>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
            <span className="font-bold text-white block font-mono text-xs">Muse Spark (muse-spark-1.3)</span>
            <span className="text-slate-400">Multimodal reasoning agent. Dispatches tool calls, evaluates visual evidence against rules, compiles checklists, and generates fix plans.</span>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-white block font-mono text-xs">Muse Voice (muse-voice-transcribe)</span>
              {transData.calls > 0 ? (
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20">Operational</span>
              ) : (
                <span className="text-[10px] font-mono text-amber-400 bg-amber-500/10 px-1.5 py-0.2 rounded border border-amber-500/20">Meta API 404 (Unavailable)</span>
              )}
            </div>
            <span className="text-slate-400">Walkthrough speech-to-text. Transcription unavailable (Meta API returned 404). Core visual inspection and safety reasoning operate independently.</span>
          </div>
        </div>
      </div>
    </section>
  );
}
