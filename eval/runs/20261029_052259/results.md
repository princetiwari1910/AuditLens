# AuditLens Evaluation Benchmark Results

> [!WARNING]
> **⚠️ SIMULATED, NOT A RESULT**
> Evaluation executed in **mock** provider mode using synthetic annotations and simulated detections.
> Results reflect local mock scenario behavior, not live Meta foundation model performance.

- **Benchmark Run Timestamp:** `20261029_052259`
- **Raw Run Directory:** [`eval/runs/20261029_052259`](eval/runs/20261029_052259)
- **Total Benchmark Clips:** 1

## 📊 Summary Performance Comparison

| Metric | Full Pipeline (AuditLens) | Vision-Chat Baseline (No Tools) | Delta (Advantage) |
|---|---|---|---|
| **Overall Accuracy** | **80.0%** | 60.0% | +20.0% |
| **Unsure Rate (Needs Review)** | 20.0% | 0.0% | Resolved by Tools |
| **Macro F1 Score** | **0.800** | 0.600 | +0.200 |
| **Macro Precision** | 1.000 | 1.000 | Calibrated Overlays |
| **Macro Recall** | 0.800 | 0.600 | Full Video Coverage |
| **Average Latency / Clip** | 0.25 s | 0.25 s | Sub-second Execution |
| **Average Cost / Clip** | $0.0000 USD | $0.0100 USD | Caching & Tool Efficiency |

## 📋 Per-Rule Detailed Evaluation

| Clip | Rule ID | Ground Truth | Pipeline | Baseline | Pipeline Match | Baseline Match | Notes |
|---|---|---|---|---|---|---|---|
| `sample_walkthrough.mp4` | `extinguisher_visible` | `pass` | `pass` | `pass` | ✅ | ✅ | Synthetic 25s walkthrough containing mou... |
| `sample_walkthrough.mp4` | `exit_sign_visible` | `pass` | `pass` | `pass` | ✅ | ✅ | Synthetic 25s walkthrough containing mou... |
| `sample_walkthrough.mp4` | `two_exits_visible` | `fail` | `unsure` | `pass` | ❌ | ❌ | Synthetic 25s walkthrough containing mou... |
| `sample_walkthrough.mp4` | `exit_path_not_blocked` | `fail` | `fail` | `fail` | ✅ | ✅ | Synthetic 25s walkthrough containing mou... |
| `sample_walkthrough.mp4` | `exit_path_clear_width` | `fail` | `fail` | `pass` | ✅ | ❌ | Synthetic 25s walkthrough containing mou... |

---

*Generated automatically by AuditLens Evaluation Harness (`eval/run_eval.py`).*
