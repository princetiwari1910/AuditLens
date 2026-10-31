# AuditLens Evaluation Benchmark Results

> [!WARNING]
> # ⚠️ MOCK, NOT A RESULT (SIMULATED, NOT A RESULT)
> **Provider Mode:** mock (simulated detections)
> Results reflect local mock scenario behavior, not live Meta foundation model performance. Comparative delta is hidden until live Meta foundation model providers are connected.

- **Benchmark Run Timestamp:** `20261031_103712`
- **Raw Run Directory:** [`eval/runs/20261031_103712`](eval/runs/20261031_103712)
- **Total Benchmark Clips:** 1

## 📊 Summary Performance Comparison

| Metric | Full Pipeline (AuditLens) | Vision-Chat Baseline (No Tools) | Delta (Advantage) |
|---|---|---|---|
| **Overall Accuracy** | **80.0%** | 60.0% | *[Hidden: needs real providers]* |
| **Unsure Rate (Needs Review)** | 20.0% | 0.0% | *[Hidden: needs real providers]* |
| **Macro F1 Score** | **0.800** | 0.600 | *[Hidden: needs real providers]* |
| **Macro Precision** | 1.000 | 1.000 | *[Hidden: needs real providers]* |
| **Macro Recall** | 0.800 | 0.600 | *[Hidden: needs real providers]* |
| **Average Latency / Clip** | 0.23 s | 0.22 s | *[Hidden: needs real providers]* |
| **Average Cost / Clip** | $0.0000 USD | $0.0100 USD | *[Hidden: needs real providers]* |

## 🔍 Confusion Matrix by Rule (AuditLens Pipeline)

| Rule ID | Ground Truth | Prediction | TP | FP | FN | TN | Precision | Recall | F1 | Abstain |
|---|---|---|---|---|---|---|---|---|---|---|
| `extinguisher_visible` | `pass` | `pass` | 0 | 0 | 0 | 1 | 1.00 | 1.00 | 1.00 | No |
| `exit_sign_visible` | `pass` | `pass` | 0 | 0 | 0 | 1 | 1.00 | 1.00 | 1.00 | No |
| `two_exits_visible` | `fail` | `unsure` | 0 | 0 | 1 | 0 | 1.00 | 0.00 | 0.00 | Yes (Unsure) |
| `exit_path_not_blocked` | `fail` | `fail` | 1 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | No |
| `exit_path_clear_width` | `fail` | `fail` | 1 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | No |

## 📋 Per-Rule Detailed Predictions

| Clip | Rule ID | Ground Truth | Pipeline | Baseline | Pipeline Match | Baseline Match | Notes |
|---|---|---|---|---|---|---|---|
| `sample_walkthrough.mp4` | `extinguisher_visible` | `pass` | `pass` | `pass` | ✅ | ✅ | Ground truth from sample_walkthrough.jso... |
| `sample_walkthrough.mp4` | `exit_sign_visible` | `pass` | `pass` | `pass` | ✅ | ✅ | Ground truth from sample_walkthrough.jso... |
| `sample_walkthrough.mp4` | `two_exits_visible` | `fail` | `unsure` | `pass` | ❌ | ❌ | Ground truth from sample_walkthrough.jso... |
| `sample_walkthrough.mp4` | `exit_path_not_blocked` | `fail` | `fail` | `fail` | ✅ | ✅ | Ground truth from sample_walkthrough.jso... |
| `sample_walkthrough.mp4` | `exit_path_clear_width` | `fail` | `fail` | `pass` | ✅ | ❌ | Ground truth from sample_walkthrough.jso... |

## ⚠️ Failure Cases & Inspection Review Table

| Clip | Rule ID | Ground Truth | Predicted | Confidence | Keyframe Link | Diagnostic Rationale |
|---|---|---|---|---|---|---|
| `sample_walkthrough.mp4` | `two_exits_visible` | `fail` | `unsure` | 0.50 | [/api/audits/eval_pipe_20261031_103712_1/frames/2](/api/audits/eval_pipe_20261031_103712_1/frames/2) | Observed 2 candidate instances, but some have marginal confidence... |

## 📈 Needs Review Calibration & Confidence Reliability

| Confidence Bin | Sample Count | Avg Confidence | Empirical Accuracy | Calibration Delta |
|---|---|---|---|---|
| `0.50-0.60` | 1 | 0.50 | 0.00 | 0.50 |
| `0.60-0.70` | 0 | 0.65 | 0.65 | 0.00 |
| `0.70-0.80` | 0 | 0.75 | 0.75 | 0.00 |
| `0.80-0.90` | 1 | 0.88 | 1.00 | 0.12 |
| `0.90-1.00` | 3 | 0.94 | 1.00 | 0.06 |

---

*Generated automatically by AuditLens Evaluation Harness (`eval/run_eval.py`).*
