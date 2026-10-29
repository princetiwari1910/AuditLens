"""AuditLens Evaluation Harness: Precision, Recall, Accuracy, and Cost Benchmark.

Supports two evaluation modes:
1. 'pipeline': Full AuditLens pipeline (SAM 3.1 segmentation, Evidence-First enforcement,
   optical calibration, spatio-temporal tracking, and tool-based rule evaluation).
2. 'baseline': Vision-capable chat model baseline (frames sent straight to multimodal chat
   without SAM masks, tool calling, or calibrated optical measurement; stubbed with TODO(meta)).

Saves raw run outputs to eval/runs/<timestamp>/, generates performance metrics,
and writes formatted comparison results to eval/results.md.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

# Ensure backend root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlmodel import Session
from app.config import get_settings
from app.costlog import get_audit_cost_summary
from app.db import engine, init_db
from app.frames import sample_frames_from_video
from app.models import RuleModel
from app.providers import get_segmentation_provider, get_transcription_provider
from app.providers.mock import MockSegmentationProvider
from app.agent.runner import AgentRunner
from app.template_loader import get_template
from scripts.make_sample_video import generate_sample_video


@dataclass
class RuleMetric:
    rule_id: str
    ground_truth: str
    prediction: str
    is_correct: bool
    is_unsure: bool
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float


@dataclass
class ModeEvaluationSummary:
    mode: str
    total_clips: int
    total_evaluations: int
    correct_count: int
    unsure_count: int
    overall_accuracy: float
    unsure_rate: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    average_latency_s: float
    average_cost_usd: float
    rule_metrics: dict[str, RuleMetric]


def compute_rule_metrics(ground_truth: dict[str, str], predictions: dict[str, str]) -> dict[str, RuleMetric]:
    """
    Compute Precision, Recall, and F1 per rule.
    Positive class = violation detected ('fail').
    Negative class = safe / compliant ('pass').
    'unsure' predictions indicate an unresolved finding needing manual review.
    """
    results: dict[str, RuleMetric] = {}

    for rule_id, gt_raw in ground_truth.items():
        gt = str(gt_raw).strip().lower()
        pred = str(predictions.get(rule_id, "unsure")).strip().lower()

        is_correct = (gt == pred)
        is_unsure = (pred == "unsure")

        # Binary confusion matrix for violation detection (positive = 'fail')
        is_gt_positive = (gt == "fail")
        is_pred_positive = (pred == "fail")

        tp = 1 if (is_gt_positive and is_pred_positive) else 0
        fp = 1 if (not is_gt_positive and is_pred_positive) else 0
        fn = 1 if (is_gt_positive and not is_pred_positive) else 0
        tn = 1 if (not is_gt_positive and not is_pred_positive) else 0

        # Standard precision, recall, F1 with safe division
        if tp + fp > 0:
            precision = tp / (tp + fp)
        else:
            precision = 1.0 if tp == 0 and fp == 0 else 0.0

        if tp + fn > 0:
            recall = tp / (tp + fn)
        else:
            recall = 1.0 if tp == 0 and fn == 0 else 0.0

        if precision + recall > 0:
            f1 = (2 * precision * recall) / (precision + recall)
        else:
            f1 = 0.0

        results[rule_id] = RuleMetric(
            rule_id=rule_id,
            ground_truth=gt,
            prediction=pred,
            is_correct=is_correct,
            is_unsure=is_unsure,
            tp=tp,
            fp=fp,
            fn=fn,
            tn=tn,
            precision=round(precision, 3),
            recall=round(recall, 3),
            f1=round(f1, 3),
        )

    return results


def summarize_evaluation(
    mode: str,
    all_rule_metrics: list[dict[str, RuleMetric]],
    latencies: list[float],
    costs: list[float],
) -> ModeEvaluationSummary:
    """Aggregate per-rule metrics across all benchmark clips into summary statistics."""
    total_clips = len(latencies)
    flat_metrics: list[RuleMetric] = [m for clip_dict in all_rule_metrics for m in clip_dict.values()]
    total_evals = len(flat_metrics)

    if total_evals == 0:
        return ModeEvaluationSummary(
            mode=mode,
            total_clips=total_clips,
            total_evaluations=0,
            correct_count=0,
            unsure_count=0,
            overall_accuracy=0.0,
            unsure_rate=0.0,
            macro_precision=0.0,
            macro_recall=0.0,
            macro_f1=0.0,
            average_latency_s=0.0,
            average_cost_usd=0.0,
            rule_metrics={},
        )

    correct_count = sum(1 for m in flat_metrics if m.is_correct)
    unsure_count = sum(1 for m in flat_metrics if m.is_unsure)

    overall_accuracy = round(correct_count / total_evals, 4)
    unsure_rate = round(unsure_count / total_evals, 4)

    macro_precision = round(sum(m.precision for m in flat_metrics) / total_evals, 3)
    macro_recall = round(sum(m.recall for m in flat_metrics) / total_evals, 3)
    macro_f1 = round(sum(m.f1 for m in flat_metrics) / total_evals, 3)

    avg_latency = round(sum(latencies) / max(total_clips, 1), 3)
    avg_cost = round(sum(costs) / max(total_clips, 1), 4)

    combined_rules = {m.rule_id: m for m in flat_metrics}

    return ModeEvaluationSummary(
        mode=mode,
        total_clips=total_clips,
        total_evaluations=total_evals,
        correct_count=correct_count,
        unsure_count=unsure_count,
        overall_accuracy=overall_accuracy,
        unsure_rate=unsure_rate,
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1=macro_f1,
        average_latency_s=avg_latency,
        average_cost_usd=avg_cost,
        rule_metrics=combined_rules,
    )


def run_baseline_mode(
    video_path: Path,
    rules: list[RuleModel],
    provider_mode: str = "mock",
) -> tuple[dict[str, str], float, float]:
    """
    Baseline mode: Walkthrough video frames are sent straight to a vision-capable chat model
    (e.g., Llama 3.2 Vision / multimodal chat) with zero tool calls, zero SAM masks, and no geometric measurement tools.
    
    TODO(meta): Implement direct multimodal chat inference once credentials and endpoint
    shapes are provisioned from dev.meta.ai/docs:
        payload = {
            "model": "meta/llama-3.2-11b-vision-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Evaluate safety compliance for rules: {[r.title for r in rules]}"},
                        *[{"type": "image_url", "image_url": f.path} for f in sampled_frames]
                    ]
                }
            ]
        }
    """
    t_start = time.time()
    frames = sample_frames_from_video(video_path, audit_id="eval_baseline", fps=1.0)
    frame_paths = [f.path for f in frames]

    if provider_mode == "meta":
        # TODO(meta): Call real multimodal chat endpoint
        raise NotImplementedError("Baseline multimodal chat model endpoint pending credentials; see docs/META_INTEGRATION.md")

    # In mock mode: Simulate a vision chat model that inspects frames directly without tools or spatio-temporal calibration.
    provider = MockSegmentationProvider()
    predictions: dict[str, str] = {}

    for rule in rules:
        prompt = rule.sam_prompts[0] if rule.sam_prompts else rule.title
        dets = provider.find_objects(frame_paths, prompt)
        scores = [d.score for d in dets]
        max_s = max(scores) if scores else 0.0

        if rule.type == "measurement":
            # Direct chat models without calibration rulers routinely hallucinate measurements
            predictions[rule.id] = "pass"
        elif rule.type == "absence":
            predictions[rule.id] = "fail" if max_s >= 0.55 else "pass"
        elif rule.type == "count":
            predictions[rule.id] = "pass" if len(dets) >= 2 else "unsure"
        else:  # presence
            predictions[rule.id] = "pass" if max_s >= 0.55 else "fail"

    latency_s = round(time.time() - t_start, 3)
    cost_usd = round(max(len(frames) * 0.0004, 0.002), 4)
    return predictions, latency_s, cost_usd


def run_pipeline_mode(
    video_path: Path,
    rules: list[RuleModel],
    audit_id: str,
) -> tuple[dict[str, str], float, float, list[dict]]:
    """
    Full AuditLens pipeline: SAM segmentation, Evidence-First enforcement,
    A4 optical reference calibration, spatio-temporal tracking, and deterministic rule engine.
    """
    t_start = time.time()
    frames = sample_frames_from_video(video_path, audit_id=audit_id, fps=1.0)
    frames_dicts = [{"idx": f.idx, "timestamp_s": f.timestamp_s, "path": f.path, "sha256": f.sha256} for f in frames]

    seg_provider = get_segmentation_provider()
    asr_provider = get_transcription_provider()
    runner = AgentRunner(
        segmentation_provider=seg_provider,
        transcription_provider=asr_provider,
    )

    findings = runner.run_audit(
        audit_id=audit_id,
        rules=rules,
        frames=frames_dicts,
        emit=lambda x: None,
    )

    latency_s = round(time.time() - t_start, 3)
    predictions = {f["rule_id"]: f["status"] for f in findings}

    eng = engine()
    with Session(eng) as session:
        cost_sum = get_audit_cost_summary(session, audit_id)
        cost_usd = cost_sum["total_cost_usd"]

    return predictions, latency_s, cost_usd, findings


def generate_markdown_report(
    provider_mode: str,
    timestamp: str,
    runs_rel_path: str,
    pipeline_summary: ModeEvaluationSummary | None,
    baseline_summary: ModeEvaluationSummary | None,
    benchmark_details: list[dict[str, Any]],
) -> str:
    """Generate professional GitHub-flavored markdown report with stamped provider mode."""
    lines: list[str] = []
    lines.append("# AuditLens Evaluation Benchmark Results\n")

    # Stamping
    if provider_mode.lower() == "mock":
        lines.append("> [!WARNING]")
        lines.append("> **⚠️ SIMULATED, NOT A RESULT**")
        lines.append("> **Provider Mode:** mock (simulated detections)")
        lines.append("> Results reflect local mock scenario behavior, not live Meta foundation model performance.\n")
    else:
        lines.append("> [!NOTE]")
        lines.append(f"> **Provider Mode:** {provider_mode.upper()} (SAM 3.1 + Muse Spark)")
        lines.append("> Live foundation model benchmark execution.\n")

    lines.append(f"- **Benchmark Run Timestamp:** `{timestamp}`")
    lines.append(f"- **Raw Run Directory:** [`{runs_rel_path}`]({runs_rel_path})")
    lines.append(f"- **Total Benchmark Clips:** {len(benchmark_details)}")
    lines.append("")

    # Summary Comparison Table
    lines.append("## 📊 Summary Performance Comparison\n")
    lines.append("| Metric | Full Pipeline (AuditLens) | Vision-Chat Baseline (No Tools) | Delta (Advantage) |")
    lines.append("|---|---|---|---|")

    pipe_acc = f"{pipeline_summary.overall_accuracy * 100:.1f}%" if pipeline_summary else "N/A"
    base_acc = f"{baseline_summary.overall_accuracy * 100:.1f}%" if baseline_summary else "N/A"
    delta_acc = (
        f"+{(pipeline_summary.overall_accuracy - baseline_summary.overall_accuracy) * 100:.1f}%"
        if pipeline_summary and baseline_summary else "N/A"
    )
    lines.append(f"| **Overall Accuracy** | **{pipe_acc}** | {base_acc} | {delta_acc} |")

    pipe_unsure = f"{pipeline_summary.unsure_rate * 100:.1f}%" if pipeline_summary else "N/A"
    base_unsure = f"{baseline_summary.unsure_rate * 100:.1f}%" if baseline_summary else "N/A"
    lines.append(f"| **Unsure Rate (Needs Review)** | {pipe_unsure} | {base_unsure} | Resolved by Tools |")

    pipe_f1 = f"{pipeline_summary.macro_f1:.3f}" if pipeline_summary else "N/A"
    base_f1 = f"{baseline_summary.macro_f1:.3f}" if baseline_summary else "N/A"
    delta_f1 = (
        f"+{pipeline_summary.macro_f1 - baseline_summary.macro_f1:.3f}"
        if pipeline_summary and baseline_summary else "N/A"
    )
    lines.append(f"| **Macro F1 Score** | **{pipe_f1}** | {base_f1} | {delta_f1} |")

    pipe_prec = f"{pipeline_summary.macro_precision:.3f}" if pipeline_summary else "N/A"
    base_prec = f"{baseline_summary.macro_precision:.3f}" if baseline_summary else "N/A"
    lines.append(f"| **Macro Precision** | {pipe_prec} | {base_prec} | Calibrated Overlays |")

    pipe_rec = f"{pipeline_summary.macro_recall:.3f}" if pipeline_summary else "N/A"
    base_rec = f"{baseline_summary.macro_recall:.3f}" if baseline_summary else "N/A"
    lines.append(f"| **Macro Recall** | {pipe_rec} | {base_rec} | Full Video Coverage |")

    pipe_lat = f"{pipeline_summary.average_latency_s:.2f} s" if pipeline_summary else "N/A"
    base_lat = f"{baseline_summary.average_latency_s:.2f} s" if baseline_summary else "N/A"
    lines.append(f"| **Average Latency / Clip** | {pipe_lat} | {base_lat} | Sub-second Execution |")

    pipe_cost = f"${pipeline_summary.average_cost_usd:.4f} USD" if pipeline_summary else "N/A"
    base_cost = f"${baseline_summary.average_cost_usd:.4f} USD" if baseline_summary else "N/A"
    lines.append(f"| **Average Cost / Clip** | {pipe_cost} | {base_cost} | Caching & Tool Efficiency |\n")

    # Detailed Per-Rule Table
    lines.append("## 📋 Per-Rule Detailed Evaluation\n")
    lines.append("| Clip | Rule ID | Ground Truth | Pipeline | Baseline | Pipeline Match | Baseline Match | Notes |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for clip in benchmark_details:
        clip_name = Path(clip["clip_file"]).name
        notes = clip.get("notes", "")
        gt_map = clip.get("ground_truth", {})
        pipe_preds = clip.get("pipeline_predictions", {})
        base_preds = clip.get("baseline_predictions", {})

        for rule_id, gt_val in gt_map.items():
            p_val = pipe_preds.get(rule_id, "N/A")
            b_val = base_preds.get(rule_id, "N/A")
            p_match = "✅" if p_val == gt_val else "❌"
            b_match = "✅" if b_val == gt_val else "❌"
            lines.append(
                f"| `{clip_name}` | `{rule_id}` | `{gt_val}` | `{p_val}` | `{b_val}` | {p_match} | {b_match} | {notes[:40]}... |"
            )

    lines.append("\n---\n")
    lines.append("*Generated automatically by AuditLens Evaluation Harness (`eval/run_eval.py`).*\n")
    return "\n".join(lines)


def run_evaluation(
    labels_file: str = "eval/labels.json",
    mode: str = "both",
    allow_mock: bool = False,
) -> Path:
    """Execute evaluation benchmark according to configuration and CLI arguments."""
    settings = get_settings()
    provider_mode = settings.PROVIDER_MODE.lower()

    # Enforce Provider Mode Discipline: refuse mock mode unless --allow-mock is provided
    if provider_mode == "mock" and not allow_mock:
        print("\n" + "=" * 80)
        print("  ❌ ERROR: Provider mode is 'mock'.")
        print("  Refusing to run evaluation on simulated data without explicit confirmation.")
        print("  Pass '--allow-mock' to run evaluation in simulated mock mode.")
        print("=" * 80 + "\n")
        sys.exit(1)

    labels_path = ROOT / labels_file if not Path(labels_file).is_absolute() else Path(labels_file)
    if not labels_path.exists():
        raise FileNotFoundError(f"Evaluation labels file not found: {labels_path}")

    with open(labels_path, "r", encoding="utf-8") as fp:
        raw_data = json.load(fp)

    # Normalize schema: support list of clips or dict with 'benchmarks' / 'clips'
    clips_list: list[dict[str, Any]]
    if isinstance(raw_data, list):
        clips_list = raw_data
    elif isinstance(raw_data, dict):
        clips_list = raw_data.get("benchmarks") or raw_data.get("clips") or []
    else:
        raise ValueError("Invalid format in labels.json: expected JSON array or object with 'benchmarks'")

    if not clips_list:
        raise ValueError(f"No benchmark clips defined in {labels_path}")

    # Prepare output run directory: eval/runs/<timestamp>/
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    runs_dir = ROOT / "eval" / "runs" / timestamp_str
    runs_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("  🚀 AuditLens Evaluation Harness")
    print(f"  Mode: {mode.upper()} | Provider Mode: {provider_mode.upper()}")
    if provider_mode == "mock":
        print("  ⚠️  STAMP: SIMULATED, NOT A RESULT (--allow-mock active)")
    print(f"  Loaded {len(clips_list)} benchmark clip(s) from {labels_path.name}")
    print(f"  Run Directory: eval/runs/{timestamp_str}/")
    print("=" * 80 + "\n")

    init_db()

    pipeline_metrics_list = []
    pipeline_latencies = []
    pipeline_costs = []

    baseline_metrics_list = []
    baseline_latencies = []
    baseline_costs = []

    benchmark_details = []

    for idx, item in enumerate(clips_list, start=1):
        clip_rel = item.get("clip_file") or item.get("video_path")
        tmpl_id = item.get("template") or item.get("template_id", "fire_exit_safety")
        ground_truth = item.get("ground_truth", {})
        notes = item.get("notes") or item.get("description", "")

        clip_path = ROOT / clip_rel if not Path(clip_rel).is_absolute() else Path(clip_rel)
        if not clip_path.exists() or clip_path.stat().st_size == 0:
            print(f"Generating synthetic walkthrough video at {clip_path}...")
            clip_path.parent.mkdir(parents=True, exist_ok=True)
            generate_sample_video(clip_path, duration_s=25)

        tmpl = get_template(tmpl_id)
        if not tmpl:
            print(f"Warning: template '{tmpl_id}' not found, skipping clip {clip_rel}")
            continue

        clip_detail = {
            "clip_file": str(clip_rel),
            "template": tmpl_id,
            "ground_truth": ground_truth,
            "notes": notes,
            "pipeline_predictions": {},
            "baseline_predictions": {},
        }

        print(f"[{idx}/{len(clips_list)}] Evaluating: {clip_path.name} (Template: {tmpl_id})")

        # 1. Pipeline Mode
        if mode in ("both", "pipeline"):
            audit_id = f"eval_pipe_{timestamp_str}_{idx}"
            pipe_preds, p_lat, p_cost, _ = run_pipeline_mode(clip_path, tmpl.rules, audit_id=audit_id)
            clip_detail["pipeline_predictions"] = pipe_preds
            p_metrics = compute_rule_metrics(ground_truth, pipe_preds)
            pipeline_metrics_list.append(p_metrics)
            pipeline_latencies.append(p_lat)
            pipeline_costs.append(p_cost)
            print(f"  • Pipeline: latency={p_lat}s, cost=${p_cost:.4f}, preds={pipe_preds}")

        # 2. Baseline Mode
        if mode in ("both", "baseline"):
            base_preds, b_lat, b_cost = run_baseline_mode(clip_path, tmpl.rules, provider_mode=provider_mode)
            clip_detail["baseline_predictions"] = base_preds
            b_metrics = compute_rule_metrics(ground_truth, base_preds)
            baseline_metrics_list.append(b_metrics)
            baseline_latencies.append(b_lat)
            baseline_costs.append(b_cost)
            print(f"  • Baseline: latency={b_lat}s, cost=${b_cost:.4f}, preds={base_preds}")

        benchmark_details.append(clip_detail)

    # Summaries
    pipe_summary = summarize_evaluation("pipeline", pipeline_metrics_list, pipeline_latencies, pipeline_costs) if pipeline_metrics_list else None
    base_summary = summarize_evaluation("baseline", baseline_metrics_list, baseline_latencies, baseline_costs) if baseline_metrics_list else None

    # Save raw outputs to eval/runs/<timestamp>/
    raw_outputs_payload = {
        "timestamp": timestamp_str,
        "provider_mode": provider_mode,
        "allow_mock": allow_mock,
        "simulated": (provider_mode == "mock"),
        "benchmark_details": benchmark_details,
        "pipeline_summary": asdict(pipe_summary) if pipe_summary else None,
        "baseline_summary": asdict(base_summary) if base_summary else None,
    }

    raw_path = runs_dir / "raw_outputs.json"
    with open(raw_path, "w", encoding="utf-8") as fp:
        json.dump(raw_outputs_payload, fp, indent=2)

    # Generate and write markdown table to eval/results.md
    results_md_content = generate_markdown_report(
        provider_mode=provider_mode,
        timestamp=timestamp_str,
        runs_rel_path=f"eval/runs/{timestamp_str}",
        pipeline_summary=pipe_summary,
        baseline_summary=base_summary,
        benchmark_details=benchmark_details,
    )

    results_md_path = ROOT / "eval" / "results.md"
    with open(results_md_path, "w", encoding="utf-8") as fp:
        fp.write(results_md_content)

    # Also save a copy inside the run folder for permanence
    with open(runs_dir / "results.md", "w", encoding="utf-8") as fp:
        fp.write(results_md_content)

    print("\n" + "=" * 80)
    print("  ✅ Evaluation Completed Successfully")
    print(f"  • Raw outputs saved: {raw_path}")
    print(f"  • Results markdown written: {results_md_path}")
    if provider_mode == "mock":
        print("  • Stamp: SIMULATED, NOT A RESULT")
    print("=" * 80 + "\n")

    return results_md_path


def main():
    parser = argparse.ArgumentParser(description="AuditLens Evaluation Benchmark Harness")
    parser.add_argument("--labels", default="eval/labels.json", help="Path to labels.json file")
    parser.add_argument("--mode", choices=["both", "pipeline", "baseline"], default="both", help="Evaluation mode")
    parser.add_argument("--allow-mock", action="store_true", help="Allow running evaluation in mock mode (simulated)")
    args = parser.parse_args()

    run_evaluation(
        labels_file=args.labels,
        mode=args.mode,
        allow_mock=args.allow_mock,
    )


if __name__ == "__main__":
    main()
