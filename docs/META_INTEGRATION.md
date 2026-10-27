# Meta Foundation Model Integration Guide

> **Phase 2 Implementation Target:** Transition from mock mode to Meta Foundation Models using the official developer portal at [dev.meta.ai/docs](https://dev.meta.ai/docs).
>
> **Target Models:**
> - **Segmentation & Grounding:** **SAM 3.1**
> - **Agent Planner & Reasoning:** **Muse Spark** (with tool-calling over `ToolRegistry`)
> - **Audio Speech-to-Text:** **Muse Voice Transcribe**

---

## 1. Architecture Overview (Zero-Refactor Transition)

AuditLens was architected using strict provider interfaces (`providers/base.py`). The agent planning engine (`agent/runner.py`) interacts exclusively with standard Python tools registered in [`ToolRegistry`](file:///Users/princetiwari19/Documents/AuditLens/backend/app/agent/tools.py#L65).

When switching from `PROVIDER_MODE=mock` to `PROVIDER_MODE=meta`, **zero database schema or API changes** are required. Simply implement the three classes in `backend/app/providers/meta.py`.

```
┌────────────────────────────────────────────────────────────────────────┐
│                          ToolRegistry                                  │
│  list_rules · find_objects · measure_clear_width · check_colocation   │
└─────────────────────────────────▲──────────────────────────────────────┘
                                  │ tool calls
┌─────────────────────────────────┴──────────────────────────────────────┐
│                    Target: Muse Spark (Planner)                        │
│            Grounded in tools; emits SSE events in real-time            │
└───────────────┬────────────────────────────────────────┬───────────────┘
                │ vision prompts                         │ audio memos
┌───────────────▼──────────────┐         ┌───────────────▼───────────────┐
│     Target: SAM 3.1          │         │ Target: Muse Voice Transcribe │
│ (Segmentation & Masks)       │         │ (Multilingual ASR)            │
└──────────────────────────────┘         └───────────────────────────────┘
```

---

## 2. Target Providers to Implement (`backend/app/providers/meta.py`)

### A. SegmentationProvider — SAM 3.1
- **Interface:** `find_objects(frame_paths: list[str], prompt: str, timestamps_s: list[float] | None = None) -> list[Detection]`
- **Input:** List of local frame file paths (JPEG) and a natural language prompt (e.g. `"fire extinguisher"`, `"box"`, `"person"`).
- **Output:** Standardized `Detection` objects:
  ```python
  Detection(
      frame_id=idx,
      timestamp_s=t,
      prompt=prompt,
      score=float(model_confidence),
      bbox={"x": float, "y": float, "w": float, "h": float},  # Normalized 0.0 to 1.0
      polygon=[[float, float], ...],                           # Normalized [x, y] coordinates
  )
  ```
- **Caching & Accounting Hook:**
  All calls automatically pass through `cache.py` (`key = sha256(frame_bytes) + "segmentation" + prompt`) and `costlog.py` using `UNIT_PRICE_SEGMENTATION`.
- **Implementation Note:**
  ```python
  # TODO(meta): Implement against dev.meta.ai/docs SAM 3.1 endpoints.
  # Normalize API bounding box output coordinates [ymin, xmin, ymax, xmax] -> {x, y, w, h} in 0..1.
  ```

### B. AgentProvider — Muse Spark (Tool Calling)
- **Interface:** `run_audit(audit: Audit, rules: list[RuleModel], tools: ToolRegistry, emit: Callable[[dict], None]) -> list[Finding]`
- **Input:** The active audit record, the rules to verify, the `ToolRegistry` exposing tool JSON Schemas (`tools.get_schemas()`), and the SSE event emitter.
- **Tool Schemas Provided:**
  - `list_rules()`
  - `find_objects(prompt: str, frame_ids: list[int] | None, min_score: float)`
  - `check_colocation(container_prompt: str, item_prompt: str, min_overlap: float)`
  - `measure_clear_width(obstacle_prompts: list[str], reference: dict)`
  - `get_voice_notes(rule_id: str | None, near_timestamp_s: float | None)`
  - `record_finding(rule_id: str, status: str, confidence: float, evidence_ids: list[str], ...)`
- **Implementation Note:**
  ```python
  # TODO(meta): Send rules and tool schemas to Muse Spark.
  # Loop over model tool-call requests, executing via tools.execute(tool_name, **args),
  # feeding tool results back to the model until record_finding is called for each rule.
  ```

### C. TranscriptionProvider — Muse Voice Transcribe
- **Interface:** `transcribe(audio_path: str, language_hint: str | None = None) -> Transcript`
- **Input:** Audio file path (WAV or WebM from the auditor voice memo).
- **Output:** Standardized `Transcript` object:
  ```python
  Transcript(
      text=full_transcript_str,
      language="hi" | "en" | "es",
      segments=[
          TranscriptSegment(start_s=0.0, end_s=3.2, text="..."),
          ...
      ]
  )
  ```
- **Implementation Note:**
  ```python
  # TODO(meta): Upload audio to Muse Voice Transcribe endpoint.
  # Map words or segment timestamps into TranscriptSegment objects.
  ```

---

## 3. Environment Variables Configuration

In `.env`:
```bash
# Switch execution provider mode
PROVIDER_MODE=meta

# Meta Developer API credentials from dev.meta.ai/docs
META_API_KEY=your_meta_developer_key_here
META_BASE_URL=https://api.meta.ai/v1

# Update with official per-unit billing rates once announced
UNIT_PRICE_SEGMENTATION=0.002    # USD per frame image (SAM 3.1)
UNIT_PRICE_AGENT_INPUT=0.003     # USD per 1K input tokens (Muse Spark)
UNIT_PRICE_AGENT_OUTPUT=0.015    # USD per 1K output tokens (Muse Spark)
UNIT_PRICE_TRANSCRIPTION=0.006   # USD per minute of audio (Muse Voice Transcribe)
```

---

## 4. Drop-in Verification Checklist

Before deploying with real Meta model access, verify:
- [ ] API Key verified with a curl request to `META_BASE_URL`.
- [ ] Implement `MetaSegmentationProvider.find_objects` with SAM 3.1.
- [ ] Implement `MetaAgentProvider.run_audit` with Muse Spark tool-calling.
- [ ] Implement `MetaTranscriptionProvider.transcribe` with Muse Voice Transcribe.
- [ ] Run benchmark evaluation suite: `python eval/run_eval.py --mode full`.
- [ ] Verify SHA-256 caching logs hits on re-runs (`GET /api/audits/{id}/cost`).
- [ ] Test with a real 30-second mobile phone walkthrough video.
