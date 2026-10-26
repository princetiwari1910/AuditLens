# Meta API Integration Plan

> **Status:** TODO(meta) — waiting for API access.
> This document will be completed in Phase 2 once we have credentials.

## Overview

When Meta API credits arrive, implement three providers in `backend/app/providers/meta.py`:

### 1. SegmentationProvider (SAM)
- **Method:** `find_objects(frame_paths, prompt) -> list[Detection]`
- **Input:** JPEG frames + text prompt
- **Output:** Normalize to `Detection(frame_id, timestamp_s, prompt, score, bbox, polygon)`
- **Env vars:** `META_API_KEY`, `META_BASE_URL`

### 2. AgentProvider (LLM Tool-Calling)
- **Method:** `run_audit(audit, rules, tools, emit) -> list[Finding]`
- **Input:** Audit context, rules, tool registry
- **Output:** The LLM plans which tools to call; results are `Finding` objects
- **Tool schemas:** Already defined in `agent/tools.py` with JSON Schema

### 3. TranscriptionProvider (ASR)
- **Method:** `transcribe(audio_path, language_hint) -> Transcript`
- **Input:** Audio file path
- **Output:** `Transcript(text, language, segments)`

## Checklist

- [ ] Get API key from dev.meta.ai/docs
- [ ] Set `META_API_KEY` and `META_BASE_URL` in `.env`
- [ ] Implement `MetaSegmentationProvider` in `providers/meta.py`
- [ ] Implement `MetaAgentProvider` in `providers/meta.py`
- [ ] Implement `MetaTranscriptionProvider` in `providers/meta.py`
- [ ] All calls go through `cache.py` and `costlog.py`
- [ ] Update `UNIT_PRICE_*` in config with real pricing
- [ ] Test with real walkthrough clips
- [ ] Set `PROVIDER_MODE=meta` in `.env`
