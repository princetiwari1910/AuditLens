"""AuditLens Evaluation Harness: Precision & Recall Benchmark Runner.

Compares two evaluation modes:
1. Baseline: Uncalibrated threshold classifier without spatio-temporal deduplication or optical reference.
2. Full Pipeline: Complete AgentRunner with Evidence-First enforcement, A4 scale calibration, and deduplication.

Usage:
    python eval/run_eval.py [--labels eval/labels.json] [--mode {both,baseline,full}]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

# Ensure backend is in python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.runner import AgentRunner
from app.frames import sample_frames_from_video
from app.models import RuleModel
from app.providers.mock import MockSegmentationProvider, MockTranscriptionProvider
from app.template_loader import get_template
from scripts.make_sample_video import generate_sample_video


def compute_metrics(predictions: dict[str, str], ground_truth: dict[str, str]) -> dict[str, dict[str, float]]:
    """
    Compute Precision, Recall, and F1 per rule.
    Positive class = non-pass violation detection (fail / unsure needing review).
    """
    rule_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})

    for rule_id, gt_status in ground_truth.items():
        pred_status = predictions.get(rule_id, "unsure")

        # Classify: Positive = finding an issue / violation ('fail' or 'unsure')
        # Negative = 'pass'
        is_gt_positive = gt_status in ("fail", "unsure")
        is_pred_positive = pred_status in ("fail", "unsure")

        if is_gt_positive and is_pred_positive:
            rule_stats[rule_id]["tp"] += 1
        elif not is_gt_positive and is_pred_positive:
            rule_stats[rule_id]["fp"] += 1
        elif is_gt_positive and not is_pred_positive:
            rule_stats[rule_id]["fn"] += 1
        else:
            rule_stats[rule_id]["tn"] += 1

    results = {}
    for rule_id, counts in rule_stats.items():
        tp = counts["tp"]
        fp = counts["fp"]
        fn = counts["fn"]

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 1.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        results[rule_id] = {
            "precision": round(precision, 2),
            "recall": round(recall, 2),
            "f1": round(f1, 2),
            "gt": ground_truth.get(rule_id, ""),
            "pred": predictions.get(rule_id, ""),
        }
    return results


def run_baseline_mode(video_path: Path, rules: list[RuleModel]) -> dict[str, str]:
    """
    Baseline mode: simplistic naive raw prompt detector without evidence tracking,
    deduplication, or optical scale reference.
    """
    provider = MockSegmentationProvider()
    frames = sample_frames_from_video(video_path, audit_id="eval_baseline", fps=1.0)
    frame_paths = [f.path for f in frames]

    predictions = {}
    for rule in rules:
        prompt = rule.sam_prompts[0] if rule.sam_prompts else rule.title
        dets = provider.find_objects(frame_paths, prompt)
        # Naive rule: if any detection score > 0.5 -> pass for presence, fail for absence
        scores = [d.score for d in dets]
        max_s = max(scores) if scores else 0.0

        if rule.type == "absence":
            predictions[rule.id] = "fail" if max_s >= 0.5 else "pass"
        else:
            predictions[rule.id] = "pass" if max_s >= 0.5 else "fail"

    return predictions


def run_full_pipeline_mode(video_path: Path, rules: list[RuleModel]) -> dict[str, str]:
    """
    Full pipeline mode: complete AgentRunner with Evidence-First enforcement,
    A4 scale calibration, and deduplication.
    """
    runner = AgentRunner(
        segmentation_provider=MockSegmentationProvider(),
        transcription_provider=MockTranscriptionProvider(),
    )
    frames = sample_frames_from_video(video_path, audit_id="eval_full", fps=1.0)
    frames_dicts = [{"idx": f.idx, "timestamp_s": f.timestamp_s, "path": f.path, "sha256": f.sha256} for f in frames]

    findings = runner.run_audit(
        audit_id="eval_full",
        rules=rules,
        frames=frames_dicts,
        emit=lambda x: None,
    )
    return {f["rule_id"]: f["status"] for f in findings}


def main():
    parser = argparse.ArgumentParser(description="AuditLens Evaluation Benchmark Suite")
    parser.add_argument("--labels", default=str(ROOT / "eval" / "labels.json"), help="Labels JSON file")
    parser.add_argument("--mode", choices=["both", "baseline", "full"], default="both")
    args = parser.parse_args()

    labels_path = Path(args.labels)
    if not labels_path.exists():
        print(f"Error: {labels_path} not found.")
        sys.exit(1)

    with open(labels_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    benchmarks = data.get("benchmarks", [])
    print("=" * 85)
    print("  AuditLens Evaluation Harness: Precision & Recall Benchmark")
    print(f"  Loaded {len(benchmarks)} benchmark target(s) from {labels_path.name}")
    print("=" * 85)

    for bench in benchmarks:
        b_id = bench.get("id")
        v_path = ROOT / bench.get("video_path")
        tmpl_id = bench.get("template_id")
        gt = bench.get("ground_truth", {})

        if not v_path.exists():
            print(f"Generating synthetic video for benchmark {b_id}...")
            generate_sample_video(v_path, duration_s=25)

        tmpl = get_template(tmpl_id)
        if not tmpl:
            print(f"Template {tmpl_id} not found, skipping.")
            continue

        print(f"\nBenchmark [{b_id}] — Checklist: {tmpl_id}")
        print(f"Ground Truth: {json.dumps(gt)}")

        if args.mode in ("both", "baseline"):
            base_preds = run_baseline_mode(v_path, tmpl.rules)
            base_metrics = compute_metrics(base_preds, gt)
            print("\n  [Mode 1: Baseline (Naive Prompt Matching)]")
            print(f"  {'RULE ID':<26} | {'GT':<6} | {'PRED':<6} | {'PREC':<6} | {'REC':<6} | {'F1':<6}")
            print("  " + "-" * 65)
            for r_id, m in base_metrics.items():
                print(f"  {r_id:<26} | {m['gt']:<6} | {m['pred']:<6} | {m['precision']:<6.2f} | {m['recall']:<6.2f} | {m['f1']:<6.2f}")

        if args.mode in ("both", "full"):
            full_preds = run_full_pipeline_mode(v_path, tmpl.rules)
            full_metrics = compute_metrics(full_preds, gt)
            print("\n  [Mode 2: Full Pipeline (Evidence-First + Optical Calibration)]")
            print(f"  {'RULE ID':<26} | {'GT':<6} | {'PRED':<6} | {'PREC':<6} | {'REC':<6} | {'F1':<6}")
            print("  " + "-" * 65)
            for r_id, m in full_metrics.items():
                print(f"  {r_id:<26} | {m['gt']:<6} | {m['pred']:<6} | {m['precision']:<6.2f} | {m['recall']:<6.2f} | {m['f1']:<6.2f}")

    print("\n" + "=" * 85)
    print("  Evaluation Run Completed.")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    main()
