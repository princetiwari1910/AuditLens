# Meta Foundation Model Integration Guide

> **STATUS:** **UNVERIFIED against live API**
> All providers (`MetaSegmenter`, `MetaReasoner`, `MetaTranscriber`) are implemented against official documentation specifications from [dev.meta.ai/docs](https://dev.meta.ai/docs) and verified offline with doc fixtures and unit tests.
> Status remains **UNVERIFIED** until `scripts/smoke_meta.py` passes with a valid live `MODEL_API_KEY`.
> Default mode remains `PROVIDER_MODE=mock`.

---

## 1. Official Documentation (Source of Truth)

All provider code is strictly built against the official developer documentation:
- **Media Segmentation & SAM:** [dev.meta.ai/docs/media-segmentation](https://dev.meta.ai/docs/media-segmentation)
- **SAM Segmenting:** [dev.meta.ai/docs/sam/segmenting](https://dev.meta.ai/docs/sam/segmenting)
- **SAM Reading Segmentation:** [dev.meta.ai/docs/sam/reading-segmentation](https://dev.meta.ai/docs/sam/reading-segmentation)
- **SAM Client Libraries:** [dev.meta.ai/docs/sam/client-libraries](https://dev.meta.ai/docs/sam/client-libraries)
- **Pricing & Rate Limits:** [dev.meta.ai/docs/pricing-rate-limits](https://dev.meta.ai/docs/pricing-rate-limits)
- **Image Understanding:** [dev.meta.ai/docs/image-understanding](https://dev.meta.ai/docs/image-understanding)
- **Structured Output:** [dev.meta.ai/docs/structured-output](https://dev.meta.ai/docs/structured-output)
- **Speech to Text:** [dev.meta.ai/docs/speech-to-text](https://dev.meta.ai/docs/speech-to-text) and `/docs/api-reference/voice/transcribe`

If any older guide disagrees with the official developer portal pages above, **the official portal pages win**.

---

## 2. Model Endpoints & Payloads

### A. MetaSegmenter (`sam-3.1`)
- **SDK:** `OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url="https://api.meta.ai/v1")`
- **API:** Responses API (`client.responses.create(...)`) with streaming enabled (`stream=True`).
- **Exact Request Payload:**
  ```json
  {
    "model": "sam-3.1",
    "input": [
      {
        "type": "input_text",
        "text": "fire extinguisher"
      },
      {
        "type": "input_image",
        "image_url": "data:image/jpeg;base64,..."
      }
    ],
    "stream": true,
    "metadata": {
      "mask_encoding": "one_bit",
      "include_confidence": "true"
    }
  }
  ```
  *(Note: Metadata dictionary values MUST be strings: `"one_bit"` and `"true"`).*

- **Prompt Sanitization:**
  - One concept per request.
  - No commas (split and take the first noun phrase).
  - No spatial descriptors (`on the left`, `to the right`, `in the middle`, `blocking`, `obstructing`).
  - No negation (`not`, `no`, `not blocked`, `unblocked`).
  - Implemented via `sanitize_concept(prompt)`.

- **Record Parsing (`meta-sam-parser>=0.0.6`):**
  - Streaming chunks are processed with `meta_sam_parser.image_segmentation_format().create_parser()` (or `video_segmentation_format()` if `SAM_VIDEO_MODE=True`).
  - The record grammar: `<0f> <object_id> <|box;x1=...;y1=...;x2=...;y2=...;w=...;h=...;c=...|> <|mask;x=0;y=0;data=H,W,!payload;c=...|>`
  - Coordinates: Box coordinates `x2` and `y2` are inclusive; `w` and `h` represent source frame dimensions. Half-open intervals:
    $$left = x_1,\quad top = y_1,\quad right = x_2 + 1,\quad bottom = y_2 + 1$$
  - Mask dimensions: $H = bottom - top$, $W = right - left$ (box-cropped).
  - Decoded using `decode_mask_to_raster(mask)` to an $H \times W$ row-major binary raster bytes.
  - Coordinate mapping: Box-cropped mask coordinates $(cx, cy)$ are mapped back to normalized full-frame coordinates:
    $$x_{norm} = \frac{left + cx}{W_{frame}},\quad y_{norm} = \frac{top + cy}{H_{frame}}$$
    *(Note: Marked with comment `# Box-cropped mask mapped back to full frame. Assumption: verify with live data.`)*
  - Key results by explicit frame marker and object ID (never stream index).
  - Empty response (0 matches) is valid and yields an empty list `[]`.
  - Cache key: `sha256(frame) + concept + model + mask_encoding`.

---

### B. MetaReasoner (`muse-spark-1.3`)
- **SDK:** `OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url="https://api.meta.ai/v1")`
- **Model ID:** `muse-spark-1.3` (Standard mode only).
- **Strict Contributor Model Rejection:** Any model ID containing `"-contributor"` (e.g. `muse-spark-1.3-contributor`) is strictly rejected via Pydantic validators and constructor checks to protect proprietary auditor and customer data from model training.
- **Image Understanding + Structured Output:**
  ```python
  client.chat.completions.create(
      model="muse-spark-1.3",
      messages=[
          {"role": "system", "content": "You are AuditLens Reasoning Agent (Muse Spark 1.3)..."},
          {"role": "user", "content": user_parts},
      ],
      response_format={
          "type": "json_schema",
          "json_schema": {
              "name": "verdict",
              "schema": SPARK_VERDICT_JSON_SCHEMA,
              "strict": True,
          },
      },
  )
  ```
- **Evidence-First Grounding:**
  - `user_parts` contains rule text, SAM visual evidence summary (boxes, scores), and keyframe images.
  - Model verdict is parsed and validated against `schemas.py` (`validate_verdict`). Any schema parsing failure defaults to `status="unsure"`.
  - Spark cannot invent evidence: `cited_frame_ids` are checked against passed keyframe IDs. Any invented frame IDs are filtered out; if no valid evidence remains for pass/fail, the verdict is downgraded to `status="unsure"`.

---

### C. MetaTranscriber (`muse-voice-transcribe-1.0`)
- **SDK:** `client.audio.transcriptions.create(model="muse-voice-transcribe-1.0", file=f, ...)`
- **Payload Limits:** Audio files are verified locally with a 25 MB limit prior to transmission.
- **Turn-Level Timestamps:**
  - Turn-level timestamps only (`TranscriptTurn(start_s=..., end_s=..., text=..., speaker=...)`).
  - No word-level timestamps.

---

## 3. Official Pricing Rates & BudgetGuard

Rates per [dev.meta.ai/docs/pricing-rate-limits](https://dev.meta.ai/docs/pricing-rate-limits):

| Capability | Model | Official Rate | AuditLens Constant |
|---|---|---|---|
| Image Segmentation | SAM 3.1 | \$2.50 / 1k images | `PRICE_SAM_PER_IMAGE_USD = 0.0025` |
| Video Segmentation | SAM 3.1 | \$0.20 / 1k frames (min 50 frames) | `PRICE_SAM_VIDEO_PER_FRAME_USD = 0.0002` |
| Reasoning (Standard) | Muse Spark 1.3 | \$1.25 / 1M input tokens | `PRICE_MUSE_SPARK_INPUT_PER_1K_USD = 0.00125` |
| Reasoning (Standard) | Muse Spark 1.3 | \$4.25 / 1M output tokens | `PRICE_MUSE_SPARK_OUTPUT_PER_1K_USD = 0.00425` |
| Voice Transcription | Muse Voice Transcribe 1.0 | \$0.18 / hour (\$0.003 / min) | `PRICE_MUSE_VOICE_PER_MIN_USD = 0.003` |

### Hardened Protection
- **Per-Audit Budget Limit:** \$1.00 (`MAX_BUDGET_PER_AUDIT_USD = 1.0`)
- **Global Dev Budget Cap:** \$20.00 (`MAX_GLOBAL_BUDGET_USD = 20.0`)
- **Team Rate Limit:** 3,000 RPM (`PROVIDER_RATE_LIMIT_RPM = 3000`)
- **HTTP 400 (Bad Request):** Never retried; raises immediately.
- **HTTP 429 (Rate Limit):** Extracts `Retry-After` header when provided, applies exponential backoff with random jitter.

---

## 4. Verification Workflow (`scripts/smoke_meta.py`)

Run the live verification smoke script:
```bash
# If MODEL_API_KEY is not set: prints instructions and exits cleanly (0)
python backend/scripts/smoke_meta.py

# When MODEL_API_KEY is available:
export MODEL_API_KEY="your_actual_meta_key"
python backend/scripts/smoke_meta.py --record
```

The script will:
1. Call Muse Spark 1.3 with a test compliance rule and verify structured verdict JSON.
2. Call SAM 3.1 Responses API with prompt `"fire extinguisher"` on a local test image, parse the response stream using `meta-sam-parser`, and output match count, bounding boxes, scores, and mask shapes.
3. Save raw responses to `data/fixtures/` if `--record` is passed.
4. Output the full verification checklist, upgrading status to **VERIFIED against live Meta API**.
