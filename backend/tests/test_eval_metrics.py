"""Unit tests for the evaluation harness metrics and provider discipline."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.run_eval import (
    compute_accuracy_vs_abstain_curve,
    compute_reliability_curve,
    compute_rule_metrics,
    generate_markdown_report,
    run_evaluation,
    summarize_evaluation,
)


def test_compute_rule_metrics_perfect_score():
    """Verify metrics when all predictions match ground truth."""
    gt = {
        "rule_extinguisher": "pass",
        "rule_exit_sign": "pass",
        "rule_exit_blocked": "fail",
        "rule_clear_width": "fail",
    }
    preds = {
        "rule_extinguisher": "pass",
        "rule_exit_sign": "pass",
        "rule_exit_blocked": "fail",
        "rule_clear_width": "fail",
    }

    metrics = compute_rule_metrics(gt, preds)
    assert len(metrics) == 4

    for r_id, m in metrics.items():
        assert m.is_correct is True
        assert m.is_unsure is False
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.f1 == 1.0


def test_compute_rule_metrics_violation_missed_and_false_positive():
    """Verify precision/recall behavior on False Negatives and False Positives."""
    gt = {
        "rule_obstacle": "fail",   # Violation present
        "rule_ppe": "pass",        # Compliant
    }
    preds = {
        "rule_obstacle": "pass",   # Missed violation -> FN
        "rule_ppe": "fail",        # False alarm -> FP
    }

    metrics = compute_rule_metrics(gt, preds)

    # Rule obstacle
    m_obs = metrics["rule_obstacle"]
    assert m_obs.is_correct is False
    assert m_obs.tp == 0
    assert m_obs.fn == 1
    assert m_obs.recall == 0.0

    # Rule ppe
    m_ppe = metrics["rule_ppe"]
    assert m_ppe.is_correct is False
    assert m_ppe.fp == 1
    assert m_ppe.precision == 0.0


def test_compute_rule_metrics_unsure_handling():
    """Unsure predictions indicate unresolved evidence needing human inspector review."""
    gt = {
        "rule_two_exits": "fail",
    }
    preds = {
        "rule_two_exits": "unsure",
    }

    metrics = compute_rule_metrics(gt, preds)
    m = metrics["rule_two_exits"]
    assert m.is_correct is False
    assert m.is_unsure is True
    assert m.fn == 1  # Did not confirm the violation


def test_summarize_evaluation_calculations():
    """Verify aggregation of accuracy, unsure rate, macro F1, latency, and cost."""
    gt = {
        "r1": "pass",
        "r2": "fail",
        "r3": "fail",
        "r4": "pass",
    }
    preds = {
        "r1": "pass",    # Correct (pass)
        "r2": "fail",    # Correct (fail)
        "r3": "unsure",  # Incorrect / Unsure
        "r4": "fail",    # Incorrect / False Positive
    }

    rule_metrics = compute_rule_metrics(gt, preds)
    latencies = [0.45, 0.55]
    costs = [0.0050, 0.0070]

    summary = summarize_evaluation(
        mode="pipeline",
        all_rule_metrics=[rule_metrics],
        latencies=latencies,
        costs=costs,
    )

    assert summary.mode == "pipeline"
    assert summary.total_clips == 2
    assert summary.total_evaluations == 4
    assert summary.correct_count == 2
    assert summary.unsure_count == 1
    assert summary.overall_accuracy == 0.5  # 2 / 4
    assert summary.unsure_rate == 0.25      # 1 / 4
    assert summary.average_latency_s == 0.5  # (0.45 + 0.55) / 2
    assert summary.average_cost_usd == 0.0060  # (0.005 + 0.007) / 2


def test_summarize_evaluation_empty_edge_case():
    """Empty evaluation returns zeroed summary metrics without dividing by zero."""
    summary = summarize_evaluation(
        mode="pipeline",
        all_rule_metrics=[],
        latencies=[],
        costs=[],
    )
    assert summary.total_evaluations == 0
    assert summary.overall_accuracy == 0.0
    assert summary.unsure_rate == 0.0
    assert summary.macro_f1 == 0.0


def test_provider_discipline_refuses_mock_without_flag(monkeypatch):
    """Refuse to run benchmark evaluation in mock mode without explicit --allow-mock flag."""
    monkeypatch.setenv("PROVIDER_MODE", "mock")

    with pytest.raises(SystemExit) as exc:
        run_evaluation(labels_file="eval/labels.json", allow_mock=False)

    assert exc.value.code == 1


def test_provider_discipline_stamps_simulated_in_mock_mode(tmp_path, monkeypatch):
    """When --allow-mock is passed, runs successfully and stamps SIMULATED, NOT A RESULT."""
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir.resolve()))

    results_path = run_evaluation(
        labels_file="eval/labels.json",
        mode="pipeline",
        allow_mock=True,
    )

    assert results_path.exists()
    content = results_path.read_text(encoding="utf-8")
    assert "SIMULATED, NOT A RESULT" in content
    assert "provider mode:** mock" in content.lower()
    assert "Overall Accuracy" in content
    assert "Full Pipeline" in content


def test_generate_markdown_report_formatting():
    """Markdown report includes summary table, delta comparisons, and per-rule entries."""
    pipe_metrics = compute_rule_metrics({"r1": "pass", "r2": "fail"}, {"r1": "pass", "r2": "fail"})
    base_metrics = compute_rule_metrics({"r1": "pass", "r2": "fail"}, {"r1": "pass", "r2": "pass"})

    pipe_sum = summarize_evaluation("pipeline", [pipe_metrics], [0.3], [0.002])
    base_sum = summarize_evaluation("baseline", [base_metrics], [0.1], [0.001])

    report = generate_markdown_report(
        provider_mode="meta",
        timestamp="20261029_100000",
        runs_rel_path="eval/runs/20261029_100000",
        pipeline_summary=pipe_sum,
        baseline_summary=base_sum,
        benchmark_details=[{
            "clip_file": "clip_01.mp4",
            "ground_truth": {"r1": "pass", "r2": "fail"},
            "pipeline_predictions": {"r1": "pass", "r2": "fail"},
            "baseline_predictions": {"r1": "pass", "r2": "pass"},
            "notes": "Sample test note",
        }],
    )

    assert "# AuditLens Evaluation Benchmark Results" in report
    assert "Provider Mode:** META" in report
    assert "| **Overall Accuracy** |" in report
    assert "| `clip_01.mp4` | `r1` | `pass` | `pass` | `pass` | ✅ | ✅ |" in report
    assert "| `clip_01.mp4` | `r2` | `fail` | `fail` | `pass` | ✅ | ❌ |" in report


def test_calibration_and_reliability_curves():
    """Verify reliability curve and accuracy vs abstain calibration computation."""
    items = [
        {"confidence": 0.95, "is_correct": True},
        {"confidence": 0.92, "is_correct": True},
        {"confidence": 0.82, "is_correct": True},
        {"confidence": 0.78, "is_correct": False},
        {"confidence": 0.62, "is_correct": False},
    ]

    rel_curve = compute_reliability_curve(items)
    assert len(rel_curve) == 5
    for b in rel_curve:
        assert "bin" in b
        assert "count" in b
        assert "accuracy" in b
        assert "confidence" in b

    abstain_curve = compute_accuracy_vs_abstain_curve(items)
    assert len(abstain_curve) > 0
    # At high threshold (0.90), low confidence items are abstained, improving accuracy
    high_t = next(c for c in abstain_curve if c["threshold"] == 0.90)
    assert high_t["abstain_rate"] > 0.0
    assert high_t["accuracy"] == 1.0  # only 0.95 and 0.92 passed through, both correct


def test_eval_latest_api_endpoint(monkeypatch, tmp_path):
    """Verify GET /api/eval/latest returns latest benchmark summary."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    res = client.get("/api/eval/latest")
    assert res.status_code == 200
    data = res.json()
    assert "timestamp" in data
    assert "provider_mode" in data
    assert "pipeline_summary" in data
    assert "reliability_curve" in data["pipeline_summary"]
    assert "accuracy_vs_abstain" in data["pipeline_summary"]

