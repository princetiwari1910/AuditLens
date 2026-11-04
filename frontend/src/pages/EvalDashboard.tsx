import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  BarChart3,
  AlertTriangle,
  TrendingUp,
  ShieldAlert,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { getLatestEval, type EvalLatestResponse } from '../api/client';

export default function EvalDashboard() {
  const [data, setData] = useState<EvalLatestResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = () => {
    setIsLoading(true);
    setError(null);
    getLatestEval()
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load evaluation benchmark data.');
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent)]" />
          <p className="text-sm font-medium text-[var(--color-text-secondary)]">
            Loading evaluation benchmark & calibration data...
          </p>
        </div>
      </div>
    );
  }

  if (error || !data || !data.pipeline_summary) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-bg)] px-6">
        <div className="max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center shadow-lg">
          <ShieldAlert className="mx-auto h-10 w-10 text-amber-500 mb-3" />
          <h2 className="text-lg font-bold text-[var(--color-text)]">Evaluation Data Unavailable</h2>
          <p className="mt-2 text-xs text-[var(--color-text-secondary)]">
            {error || 'No evaluation benchmark runs recorded yet.'}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              to="/"
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] px-4 py-2 text-xs font-semibold text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Home
            </Link>
            <button
              onClick={loadData}
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--color-accent)] px-4 py-2 text-xs font-semibold text-white"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  const pSum = data.pipeline_summary;
  const isMock = data.provider_mode.toLowerCase() === 'mock';
  const relCurve = pSum.reliability_curve || [];
  const accAbstain = pSum.accuracy_vs_abstain || [];

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      {/* Top Header */}
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 sm:px-6 py-3.5 sticky top-0 z-20">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-2">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors shrink-0 min-h-[36px]"
          >
            <ArrowLeft className="h-4 w-4" />
            Home
          </Link>
          <div className="flex items-center gap-2 shrink-0">
            {isMock ? (
              <span className="rounded-full bg-amber-500/20 px-2.5 sm:px-3 py-1 text-[11px] sm:text-xs font-bold text-amber-700 dark:text-amber-300 border border-amber-500/30">
                <span className="hidden sm:inline">MOCK (SIMULATED, NOT A RESULT)</span>
                <span className="sm:hidden">MOCK (SIMULATED)</span>
              </span>
            ) : (
              <span className="rounded-full bg-blue-500/20 px-2.5 sm:px-3 py-1 text-[11px] sm:text-xs font-bold text-blue-700 dark:text-blue-300 border border-blue-500/30">
                LIVE {data.provider_mode.toUpperCase()}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8 space-y-8">
        {/* Prominent MOCK Banner */}
        {isMock && (
          <div className="rounded-xl border-2 border-amber-500/40 bg-amber-500/15 p-5 text-sm font-medium text-amber-900 dark:text-amber-200 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="font-extrabold uppercase tracking-wider bg-amber-500/30 text-amber-900 dark:text-amber-100 px-2.5 py-1 rounded text-xs border border-amber-500/40">
                ⚠️ MOCK, NOT A RESULT
              </span>
              <span className="text-sm font-bold">Simulated benchmark execution</span>
            </div>
            <p className="mt-2 text-xs text-amber-800 dark:text-amber-300">
              Evaluation executed in <strong>mock mode</strong> using synthetic annotations and simulated detections.
              Pipeline-vs-baseline comparison delta is hidden ("needs real providers").
            </p>
          </div>
        )}

        {/* Title */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-[var(--color-text)]">
              Evaluation & Calibration Dashboard
            </h1>
            <p className="text-xs text-[var(--color-text-secondary)] mt-1">
              Empirical Precision, Recall, Confusion Matrices, and Needs Review Abstain Calibration.
            </p>
          </div>
          <span className="text-xs font-mono text-[var(--color-text-secondary)]">
            Run: {data.timestamp}
          </span>
        </div>

        {/* Summary Comparison: Pipeline vs Baseline */}
        {data.pipeline_summary && (
          <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 space-y-4 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[var(--color-border)] pb-3">
              <div>
                <h3 className="text-base font-bold text-[var(--color-text)] flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-[var(--color-accent)]" />
                  Pipeline vs Vision-Chat Baseline Performance
                </h3>
                <p className="text-xs text-[var(--color-text-secondary)]">
                  Comparison between full AuditLens pipeline and baseline vision model.
                </p>
              </div>
              {isMock && (
                <span className="text-xs font-mono font-semibold text-amber-600 dark:text-amber-400">
                  Needs real providers to compute comparison delta
                </span>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[var(--color-text-secondary)] uppercase text-[10px]">
                    <th className="py-2.5 px-3">Metric</th>
                    <th className="py-2.5 px-3">Full Pipeline (AuditLens)</th>
                    <th className="py-2.5 px-3">Vision-Chat Baseline (No Tools)</th>
                    <th className="py-2.5 px-3">Delta (Advantage)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  <tr>
                    <td className="py-2.5 px-3 font-semibold text-[var(--color-text)]">Overall Accuracy</td>
                    <td className="py-2.5 px-3 font-bold text-green-700 dark:text-green-400">
                      {(pSum.overall_accuracy * 100).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 text-[var(--color-text-secondary)]">
                      {data.baseline_summary ? `${(data.baseline_summary.overall_accuracy * 100).toFixed(1)}%` : 'N/A'}
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-slate-500">
                      {isMock
                        ? 'needs real providers'
                        : data.baseline_summary
                        ? `+${((pSum.overall_accuracy - data.baseline_summary.overall_accuracy) * 100).toFixed(1)}%`
                        : 'N/A'}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-semibold text-[var(--color-text)]">Macro F1 Score</td>
                    <td className="py-2.5 px-3 font-bold text-[var(--color-text)]">{pSum.macro_f1.toFixed(3)}</td>
                    <td className="py-2.5 px-3 text-[var(--color-text-secondary)]">
                      {data.baseline_summary ? data.baseline_summary.macro_f1.toFixed(3) : 'N/A'}
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-slate-500">
                      {isMock
                        ? 'needs real providers'
                        : data.baseline_summary
                        ? `+${(pSum.macro_f1 - data.baseline_summary.macro_f1).toFixed(3)}`
                        : 'N/A'}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-semibold text-[var(--color-text)]">Unsure Rate (Needs Review)</td>
                    <td className="py-2.5 px-3 text-amber-600 dark:text-amber-400">{(pSum.unsure_rate * 100).toFixed(1)}%</td>
                    <td className="py-2.5 px-3 text-[var(--color-text-secondary)]">
                      {data.baseline_summary ? `${(data.baseline_summary.unsure_rate * 100).toFixed(1)}%` : 'N/A'}
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-slate-500">
                      {isMock ? 'needs real providers' : 'Resolved by Tools'}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2.5 px-3 font-semibold text-[var(--color-text)]">Average Cost / Clip</td>
                    <td className="py-2.5 px-3 font-bold text-[var(--color-text)]">${pSum.average_cost_usd.toFixed(4)}</td>
                    <td className="py-2.5 px-3 text-[var(--color-text-secondary)]">
                      {data.baseline_summary ? `$${data.baseline_summary.average_cost_usd.toFixed(4)}` : 'N/A'}
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-slate-500">
                      {isMock ? 'needs real providers' : 'Tool & Cache Efficiency'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* KPI Summary Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 font-mono">
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <span className="text-[11px] text-[var(--color-text-secondary)] block">Overall Accuracy</span>
            <span className="text-xl font-bold text-green-700 dark:text-green-400">
              {(pSum.overall_accuracy * 100).toFixed(1)}%
            </span>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <span className="text-[11px] text-[var(--color-text-secondary)] block">Needs Review (Abstain)</span>
            <span className="text-xl font-bold text-amber-600 dark:text-amber-400">
              {(pSum.unsure_rate * 100).toFixed(1)}%
            </span>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <span className="text-[11px] text-[var(--color-text-secondary)] block">Macro F1 Score</span>
            <span className="text-xl font-bold text-[var(--color-text)]">
              {pSum.macro_f1.toFixed(3)}
            </span>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <span className="text-[11px] text-[var(--color-text-secondary)] block">Macro Precision</span>
            <span className="text-xl font-bold text-[var(--color-text)]">
              {pSum.macro_precision.toFixed(3)}
            </span>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <span className="text-[11px] text-[var(--color-text-secondary)] block">Avg Latency / Clip</span>
            <span className="text-xl font-bold text-[var(--color-text)]">
              {pSum.average_latency_s.toFixed(2)}s
            </span>
          </div>

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <span className="text-[11px] text-[var(--color-text-secondary)] block">Avg Cost / Clip</span>
            <span className="text-xl font-bold text-green-700 dark:text-green-400">
              ${pSum.average_cost_usd.toFixed(4)}
            </span>
          </div>
        </div>

        {/* Charts Section: Reliability Diagram & Accuracy-vs-Abstain Curve */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Chart 1: Reliability Diagram */}
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 space-y-4 shadow-sm">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3">
              <div>
                <h3 className="text-sm font-bold text-[var(--color-text)] flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-[var(--color-accent)]" />
                  Reliability Diagram (Confidence vs Accuracy)
                </h3>
                <p className="text-[11px] text-[var(--color-text-secondary)]">
                  Well-calibrated models align with the diagonal dashed line.
                </p>
              </div>
            </div>

            {/* SVG Calibration Chart */}
            <div className="relative h-64 w-full">
              <svg className="h-full w-full overflow-visible" viewBox="0 0 400 220">
                {/* Grid Lines */}
                <line x1="40" y1="20" x2="380" y2="20" stroke="currentColor" className="text-slate-200 dark:text-slate-800" strokeWidth="1" />
                <line x1="40" y1="65" x2="380" y2="65" stroke="currentColor" className="text-slate-200 dark:text-slate-800" strokeWidth="1" />
                <line x1="40" y1="110" x2="380" y2="110" stroke="currentColor" className="text-slate-200 dark:text-slate-800" strokeWidth="1" />
                <line x1="40" y1="155" x2="380" y2="155" stroke="currentColor" className="text-slate-200 dark:text-slate-800" strokeWidth="1" />
                <line x1="40" y1="200" x2="380" y2="200" stroke="currentColor" className="text-slate-300 dark:text-slate-700" strokeWidth="1.5" />
                <line x1="40" y1="20" x2="40" y2="200" stroke="currentColor" className="text-slate-300 dark:text-slate-700" strokeWidth="1.5" />

                {/* Perfect Calibration Diagonal Line */}
                <line x1="40" y1="200" x2="380" y2="20" stroke="currentColor" className="text-slate-400 dark:text-slate-600" strokeDasharray="4 4" strokeWidth="1.5" />

                {/* Bars for bins */}
                {relCurve.map((b, i) => {
                  const x = 55 + i * 65;
                  const barH = b.accuracy * 180;
                  const y = 200 - barH;
                  return (
                    <g key={b.bin}>
                      <rect
                        x={x}
                        y={y}
                        width="38"
                        height={barH}
                        rx="4"
                        className="fill-[var(--color-accent)] opacity-80 hover:opacity-100 transition-opacity"
                      />
                      <text x={x + 19} y={y - 6} textAnchor="middle" className="text-[10px] font-mono fill-current text-[var(--color-text)]">
                        {(b.accuracy * 100).toFixed(0)}%
                      </text>
                      <text x={x + 19} y="215" textAnchor="middle" className="text-[9px] font-mono fill-current text-[var(--color-text-secondary)]">
                        {b.bin}
                      </text>
                    </g>
                  );
                })}

                {/* Y-axis labels */}
                <text x="32" y="24" textAnchor="end" className="text-[9px] font-mono fill-current text-[var(--color-text-secondary)]">1.0</text>
                <text x="32" y="114" textAnchor="end" className="text-[9px] font-mono fill-current text-[var(--color-text-secondary)]">0.5</text>
                <text x="32" y="204" textAnchor="end" className="text-[9px] font-mono fill-current text-[var(--color-text-secondary)]">0.0</text>
              </svg>
            </div>
            <div className="flex items-center justify-between text-[11px] text-[var(--color-text-secondary)] pt-2 border-t border-[var(--color-border)]">
              <span>X-axis: Model Confidence Bins</span>
              <span>Y-axis: Empirical Accuracy</span>
            </div>
          </div>

          {/* Chart 2: Accuracy vs Abstain Curve */}
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 space-y-4 shadow-sm">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3">
              <div>
                <h3 className="text-sm font-bold text-[var(--color-text)] flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-green-600 dark:text-green-400" />
                  Accuracy vs Abstain Curve ("Needs Review")
                </h3>
                <p className="text-[11px] text-[var(--color-text-secondary)]">
                  Trade-off between automation coverage and decision certainty.
                </p>
              </div>
            </div>

            {/* SVG Accuracy-vs-Abstain Line Chart */}
            <div className="relative h-64 w-full">
              <svg className="h-full w-full overflow-visible" viewBox="0 0 400 220">
                {/* Grid */}
                <line x1="40" y1="20" x2="380" y2="20" stroke="currentColor" className="text-slate-200 dark:text-slate-800" strokeWidth="1" />
                <line x1="40" y1="110" x2="380" y2="110" stroke="currentColor" className="text-slate-200 dark:text-slate-800" strokeWidth="1" />
                <line x1="40" y1="200" x2="380" y2="200" stroke="currentColor" className="text-slate-300 dark:text-slate-700" strokeWidth="1.5" />
                <line x1="40" y1="20" x2="40" y2="200" stroke="currentColor" className="text-slate-300 dark:text-slate-700" strokeWidth="1.5" />

                {/* Polylines for Accuracy and Abstain Rate */}
                {accAbstain.length > 1 && (
                  <>
                    {/* Accuracy Line (Green) */}
                    <polyline
                      fill="none"
                      stroke="#16a34a"
                      strokeWidth="3"
                      points={accAbstain
                        .map((pt, idx) => {
                          const x = 50 + idx * (310 / (accAbstain.length - 1));
                          const y = 200 - pt.accuracy * 180;
                          return `${x},${y}`;
                        })
                        .join(' ')}
                    />
                    {/* Abstain Line (Amber) */}
                    <polyline
                      fill="none"
                      stroke="#d97706"
                      strokeWidth="2.5"
                      strokeDasharray="4 3"
                      points={accAbstain
                        .map((pt, idx) => {
                          const x = 50 + idx * (310 / (accAbstain.length - 1));
                          const y = 200 - pt.abstain_rate * 180;
                          return `${x},${y}`;
                        })
                        .join(' ')}
                    />

                    {accAbstain.map((pt, idx) => {
                      const x = 50 + idx * (310 / (accAbstain.length - 1));
                      const yAcc = 200 - pt.accuracy * 180;
                      return (
                        <circle key={pt.threshold} cx={x} cy={yAcc} r="4" className="fill-green-600 stroke-white dark:stroke-black" strokeWidth="1.5" />
                      );
                    })}
                  </>
                )}

                {/* X-axis labels */}
                {accAbstain.map((pt, idx) => {
                  const x = 50 + idx * (310 / (accAbstain.length - 1));
                  return (
                    <text key={idx} x={x} y="215" textAnchor="middle" className="text-[9px] font-mono fill-current text-[var(--color-text-secondary)]">
                      {pt.threshold.toFixed(2)}
                    </text>
                  );
                })}

                {/* Y-axis */}
                <text x="32" y="24" textAnchor="end" className="text-[9px] font-mono fill-current text-[var(--color-text-secondary)]">1.0</text>
                <text x="32" y="114" textAnchor="end" className="text-[9px] font-mono fill-current text-[var(--color-text-secondary)]">0.5</text>
                <text x="32" y="204" textAnchor="end" className="text-[9px] font-mono fill-current text-[var(--color-text-secondary)]">0.0</text>
              </svg>
            </div>
            <div className="flex items-center justify-between text-[11px] text-[var(--color-text-secondary)] pt-2 border-t border-[var(--color-border)]">
              <span className="flex items-center gap-2">
                <span className="h-2 w-4 bg-green-600 rounded" /> Accuracy on decided cases
                <span className="h-2 w-4 border-t-2 border-dashed border-amber-600" /> Abstain rate
              </span>
              <span>X-axis: Confidence Threshold</span>
            </div>
          </div>
        </div>

        {/* Confusion Matrix Table */}
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 space-y-4 shadow-sm">
          <h3 className="text-base font-bold text-[var(--color-text)]">
            Per-Rule Confusion Matrix & Verification Metrics
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-[var(--color-text-secondary)] uppercase text-[10px]">
                  <th className="py-2.5 px-3">Rule ID</th>
                  <th className="py-2.5 px-3">GT</th>
                  <th className="py-2.5 px-3">Pred</th>
                  <th className="py-2.5 px-2 text-center">TP</th>
                  <th className="py-2.5 px-2 text-center">FP</th>
                  <th className="py-2.5 px-2 text-center">FN</th>
                  <th className="py-2.5 px-2 text-center">TN</th>
                  <th className="py-2.5 px-3 text-right">Precision</th>
                  <th className="py-2.5 px-3 text-right">Recall</th>
                  <th className="py-2.5 px-3 text-right">F1</th>
                  <th className="py-2.5 px-3 text-center">Needs Review</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {Object.entries(pSum.rule_metrics).map(([rId, m]: [string, any]) => (
                  <tr key={rId} className="hover:bg-[var(--color-bg-secondary)]/50">
                    <td className="py-2.5 px-3 font-semibold text-[var(--color-text)]">{rId}</td>
                    <td className="py-2.5 px-3 uppercase text-[var(--color-text-secondary)]">{m.ground_truth}</td>
                    <td className="py-2.5 px-3 uppercase font-bold text-[var(--color-text)]">{m.prediction}</td>
                    <td className="py-2.5 px-2 text-center text-slate-500">{m.tp}</td>
                    <td className="py-2.5 px-2 text-center text-slate-500">{m.fp}</td>
                    <td className="py-2.5 px-2 text-center text-slate-500">{m.fn}</td>
                    <td className="py-2.5 px-2 text-center text-slate-500">{m.tn}</td>
                    <td className="py-2.5 px-3 text-right font-bold text-green-700 dark:text-green-400">
                      {(m.precision * 100).toFixed(0)}%
                    </td>
                    <td className="py-2.5 px-3 text-right font-bold text-green-700 dark:text-green-400">
                      {(m.recall * 100).toFixed(0)}%
                    </td>
                    <td className="py-2.5 px-3 text-right font-bold text-[var(--color-text)]">
                      {m.f1.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      {m.is_unsure ? (
                        <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                          Yes (Review)
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Failure Cases Table */}
        {pSum.failure_cases && pSum.failure_cases.length > 0 && (
          <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 space-y-4 shadow-sm">
            <h3 className="text-base font-bold text-[var(--color-text)] flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Inspection Review Cases (Abstentions & Mismatches)
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[var(--color-text-secondary)] font-mono text-[10px] uppercase">
                    <th className="py-2.5 px-3">Clip</th>
                    <th className="py-2.5 px-3">Rule</th>
                    <th className="py-2.5 px-3">Ground Truth</th>
                    <th className="py-2.5 px-3">Predicted</th>
                    <th className="py-2.5 px-3">Keyframe Link</th>
                    <th className="py-2.5 px-3">Diagnostic Rationale</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {pSum.failure_cases.map((fc: any, i: number) => (
                    <tr key={i} className="hover:bg-[var(--color-bg-secondary)]/50">
                      <td className="py-2.5 px-3 font-mono font-medium">{fc.clip_file}</td>
                      <td className="py-2.5 px-3 font-mono font-semibold">{fc.rule_id}</td>
                      <td className="py-2.5 px-3 font-mono uppercase text-slate-500">{fc.ground_truth}</td>
                      <td className="py-2.5 px-3 font-mono uppercase font-bold text-amber-600 dark:text-amber-400">
                        {fc.prediction}
                      </td>
                      <td className="py-2.5 px-3 font-mono">
                        <a
                          href={fc.frame_link}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[var(--color-accent)] hover:underline"
                        >
                          Frame #{fc.frame_idx} ({fc.timestamp_s}s)
                        </a>
                      </td>
                      <td className="py-2.5 px-3 text-xs text-[var(--color-text-secondary)]">
                        {fc.rationale}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
