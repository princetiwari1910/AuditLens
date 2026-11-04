#!/usr/bin/env python3
"""Live smoke test for Meta Foundation Models (SAM 3.1, Muse Spark 1.3, Muse Voice Transcribe 1.0).

Each step (Spark, SAM, Voice) is independent: a failure in one does NOT skip the others.
At the end, prints a summary table: step, PASS/FAIL, latency, estimated cost, error.

Exit code 1 if any step fails or MODEL_API_KEY is missing.
Supports --record to save raw responses to data/fixtures/ for offline replay.
Supports --image for a custom photo, --audio for a voice file.
Supports --concepts "a,b,c" for SAM (one request per concept, validated by concept_validation).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Add backend directory to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import cv2
import numpy as np

from app.config import get_settings
from app.concept_validation import validate_concept
from app.providers.client import estimate_reasoner_cost, estimate_segmentation_cost, estimate_transcription_cost


@dataclass
class StepResult:
    name: str
    status: str = "SKIP"
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    error: str = ""
    details: list[str] = field(default_factory=list)


def ensure_test_image(data_dir: Path) -> Path:
    """Ensure a sample image with a fire extinguisher illustration exists for SAM smoke test."""
    photos_dir = data_dir / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    img_path = photos_dir / "smoke_test_frame.jpg"
    if img_path.exists():
        return img_path

    # Create a 640x480 test image with a red cylinder representing a fire extinguisher
    img = np.full((480, 640, 3), 235, dtype=np.uint8)  # Off-white wall
    # Red cylinder (fire extinguisher body)
    cv2.rectangle(img, (260, 160), (360, 360), (30, 30, 200), -1)
    # Nozzle / handle
    cv2.rectangle(img, (290, 120), (330, 160), (50, 50, 50), -1)
    cv2.putText(
        img,
        "FIRE EXTINGUISHER",
        (265, 260),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (255, 255, 255),
        1,
    )
    cv2.imwrite(str(img_path), img)
    return img_path


def draw_overlay(
    image_path: Path,
    concept: str,
    detections: list,
    output_dir: Path,
) -> Path | None:
    """Draw bounding boxes and mask contours on the image, save as overlay_<concept>.png."""
    try:
        img = cv2.imread(str(image_path))
        if img is None:
            return None

        h, w = img.shape[:2]
        for det in detections:
            box = det.box
            x1 = int(box["x"] * w)
            y1 = int(box["y"] * h)
            x2 = int((box["x"] + box["w"]) * w)
            y2 = int((box["y"] + box["h"]) * h)

            # Draw bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{concept} ({det.score:.2f})"
            cv2.putText(img, label, (x1, max(y1 - 8, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # Draw mask contour if available
            if isinstance(det.mask, list) and len(det.mask) >= 3:
                pts = np.array(
                    [[int(p[0] * w), int(p[1] * h)] for p in det.mask],
                    dtype=np.int32,
                )
                cv2.polylines(img, [pts], isClosed=True, color=(255, 0, 0), thickness=2)

        safe_concept = concept.replace(" ", "_").replace("/", "_")
        out_path = output_dir / f"overlay_{safe_concept}.png"
        output_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), img)
        return out_path
    except Exception:
        return None


def run_spark_step(fixtures_dir: Path, record: bool) -> StepResult:
    """Test Muse Spark 1.3 (Reasoner & Structured Output)."""
    from app.providers.meta import MetaAgentProvider

    result = StepResult(name="Spark (verdict)")
    t0 = time.perf_counter()
    try:
        spark = MetaAgentProvider()
        verdict = spark.judge(
            rule={"title": "Emergency exit sign visibility", "description": "Exit sign must be clearly visible."},
            evidence=[{"frame_id": 0, "label": "exit sign", "score": 0.95}],
        )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.cost_usd = estimate_reasoner_cost(1.0, 0.25)
        result.status = "PASS"
        result.details.append(f"status={verdict.get('status')}")
        result.details.append(f"confidence={verdict.get('confidence')}")

        if record:
            fixtures_dir.mkdir(parents=True, exist_ok=True)
            (fixtures_dir / "spark_smoke_fixture.json").write_text(
                json.dumps(verdict, indent=2), encoding="utf-8"
            )
    except Exception as exc:
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.status = "FAIL"
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def run_spark_vision_step(
    image_path: Path,
    concept: str,
    fixtures_dir: Path,
    record: bool,
) -> StepResult:
    """Test Muse Spark 1.3 Vision (Image understanding & Presence Verification)."""
    from app.providers.meta import MetaAgentProvider

    result = StepResult(name="Spark vision")
    t0 = time.perf_counter()
    try:
        spark = MetaAgentProvider()
        presence = spark.verify_presence(
            concept=concept,
            frames=[{"idx": 0, "path": str(image_path)}],
        )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.cost_usd = estimate_reasoner_cost(0.5, 0.1)
        result.status = "PASS"
        result.details.append(f"concept='{concept}'")
        result.details.append(f"present={presence.get('present')}")
        result.details.append(f"cited_frame_ids={presence.get('cited_frame_ids')}")
        result.details.append(f"rationale={presence.get('rationale')}")

        if record:
            fixtures_dir.mkdir(parents=True, exist_ok=True)
            (fixtures_dir / "spark_vision_smoke_fixture.json").write_text(
                json.dumps(presence, indent=2), encoding="utf-8"
            )
    except Exception as exc:
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.status = "FAIL"
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def run_sam_step(
    image_path: Path,
    concepts: list[str],
    fixtures_dir: Path,
    photos_dir: Path,
    record: bool,
) -> StepResult:
    """Test SAM 3.1 (Responses API Streaming & Masks)."""
    from app.providers.meta import MetaSegmentationProvider

    result = StepResult(name="SAM (segment)")
    t0 = time.perf_counter()
    try:
        sam = MetaSegmentationProvider()
        all_detections = []

        for concept in concepts:
            validated = validate_concept(concept)
            dets = sam.segment(image_path, [validated])
            all_detections.extend(dets)

            # Print per-concept results
            result.details.append(f"concept='{validated}': {len(dets)} matches")
            for idx, det in enumerate(dets):
                mask_shape = f"{len(det.mask)} pts" if isinstance(det.mask, list) else "none"
                result.details.append(
                    f"  match {idx+1}: score={det.score:.3f}, box={det.box}, mask={mask_shape}"
                )

            # Draw overlay
            overlay_path = draw_overlay(image_path, validated, dets, photos_dir)
            if overlay_path:
                result.details.append(f"  overlay: {overlay_path}")

        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.cost_usd = estimate_segmentation_cost(len(concepts))
        result.status = "PASS"

        if record:
            fixtures_dir.mkdir(parents=True, exist_ok=True)
            record_data = [
                {"label": d.label, "score": d.score, "box": d.box, "mask": d.mask}
                for d in all_detections
            ]
            (fixtures_dir / "sam_smoke_fixture.json").write_text(
                json.dumps(record_data, indent=2), encoding="utf-8"
            )
    except Exception as exc:
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.status = "FAIL"
        result.error = f"{type(exc).__name__}: {exc}"
        # On any 400 or error, print the request SHAPE with image bytes redacted for diffing
        try:
            from app.providers.meta import (
                build_sam_request_input,
                encode_image_to_base64_data_url,
                redact_sam_input_shape,
            )
            data_url, _, _, _ = encode_image_to_base64_data_url(image_path)
            sample_input = build_sam_request_input(concepts[0] if concepts else "fire extinguisher", data_url)
            redacted_shape = redact_sam_input_shape(sample_input)
            result.details.append("SAM Request Shape (image bytes redacted):")
            result.details.append(json.dumps(redacted_shape, indent=2))
        except Exception as shape_err:
            result.details.append(f"Could not build redacted request shape: {shape_err}")

    return result


def run_voice_step(audio_path: Path, fixtures_dir: Path, record: bool) -> StepResult:
    """Test Muse Voice Transcribe 1.0."""
    from app.providers.meta import MetaTranscriptionProvider

    result = StepResult(name="Voice (transcribe)")
    t0 = time.perf_counter()
    try:
        asr = MetaTranscriptionProvider()
        transcript = asr.transcribe(str(audio_path))
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.cost_usd = estimate_transcription_cost(1.0)
        result.status = "PASS"
        result.details.append(f"text={transcript.text[:80]}...")
        result.details.append(f"turns={len(transcript.turns)}")
        result.details.append(f"language={transcript.language}")

        if record:
            fixtures_dir.mkdir(parents=True, exist_ok=True)
            (fixtures_dir / "voice_smoke_fixture.json").write_text(
                json.dumps({
                    "text": transcript.text,
                    "language": transcript.language,
                    "turns": [{"start_s": t.start_s, "end_s": t.end_s, "text": t.text} for t in transcript.turns],
                }, indent=2), encoding="utf-8"
            )
    except Exception as exc:
        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.status = "FAIL"
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def print_table(results: list[StepResult]) -> None:
    """Print a summary table."""
    print()
    print(f"{'Step':<25} {'Status':<8} {'Latency':<12} {'Est. Cost':<12} {'Error'}")
    print("-" * 90)
    for r in results:
        latency_str = f"{r.latency_ms:.0f} ms" if r.latency_ms > 0 else "-"
        cost_str = f"${r.cost_usd:.5f}" if r.cost_usd > 0 else "-"
        error_str = r.error[:40] if r.error else "-"
        print(f"{r.name:<25} {r.status:<8} {latency_str:<12} {cost_str:<12} {error_str}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AuditLens Live Smoke Test for Meta Foundation Models."
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Record raw responses to data/fixtures/ for offline replay.",
    )
    parser.add_argument(
        "--image",
        type=str,
        default="",
        help="Path to custom image file for SAM 3.1 testing.",
    )
    parser.add_argument(
        "--audio",
        type=str,
        default="",
        help="Optional path to audio file for Muse Voice Transcribe testing.",
    )
    parser.add_argument(
        "--concepts",
        type=str,
        default="fire extinguisher",
        help="Comma-separated SAM concepts (one request per concept). Default: 'fire extinguisher'.",
    )
    args = parser.parse_args()

    settings = get_settings()
    api_key = os.environ.get("MODEL_API_KEY") or settings.MODEL_API_KEY or settings.META_API_KEY

    print("=" * 80)
    print("AuditLens: Meta Foundation Models Smoke Test (dev.meta.ai)")
    print("=" * 80)

    if not api_key:
        print("NOT VERIFIED: no key")
        print()
        print("Set MODEL_API_KEY to run against the live Meta developer APIs.")
        print("  export MODEL_API_KEY=\"your_meta_api_key_here\"")
        print("=" * 80)
        return 1

    print("MODEL_API_KEY detected. Connecting to https://api.meta.ai/v1...")

    fixtures_dir = settings.DATA_DIR / "fixtures"
    photos_dir = settings.DATA_DIR / "photos"

    # Parse concepts
    concepts = [c.strip() for c in args.concepts.split(",") if c.strip()]
    # Validate all concepts upfront
    for c in concepts:
        try:
            validate_concept(c)
        except ValueError as e:
            print(f"ERROR: Invalid concept: {e}")
            return 1

    # Determine image path
    if args.image:
        img_path = Path(args.image)
        if not img_path.exists():
            print(f"ERROR: Specified image file does not exist: {img_path}")
            return 1
    else:
        img_path = ensure_test_image(settings.DATA_DIR)
    print(f"Image: {img_path}")
    print(f"Concepts: {concepts}")

    results: list[StepResult] = []

    # 1. Spark
    print("\n--- 1. Muse Spark 1.3 (Reasoner) ---")
    spark_result = run_spark_step(fixtures_dir, args.record)
    for d in spark_result.details:
        print(f"  {d}")
    if spark_result.error:
        print(f"  ERROR: {spark_result.error}")
    results.append(spark_result)

    # 2. Spark vision (Presence Verification via verify_presence)
    first_concept = concepts[0] if concepts else "fire extinguisher"
    print(f"\n--- 2. Muse Spark Vision (Presence Verification: '{first_concept}') ---")
    spark_vision_result = run_spark_vision_step(img_path, first_concept, fixtures_dir, args.record)
    for d in spark_vision_result.details:
        print(f"  {d}")
    if spark_vision_result.error:
        print(f"  ERROR: {spark_vision_result.error}")
    results.append(spark_vision_result)

    # 3. SAM
    print("\n--- 3. SAM 3.1 (Segmentation) ---")
    sam_result = run_sam_step(img_path, concepts, fixtures_dir, photos_dir, args.record)
    for d in sam_result.details:
        print(f"  {d}")
    if sam_result.error:
        print(f"  ERROR: {sam_result.error}")
    results.append(sam_result)

    # 4. Voice (only if --audio provided)
    if args.audio:
        audio_path = Path(args.audio)
        if audio_path.exists():
            print(f"\n--- 4. Muse Voice Transcribe ({audio_path.name}) ---")
            voice_result = run_voice_step(audio_path, fixtures_dir, args.record)
            for d in voice_result.details:
                print(f"  {d}")
            if voice_result.error:
                print(f"  ERROR: {voice_result.error}")
            results.append(voice_result)
        else:
            print(f"\n--- 4. Muse Voice Transcribe ---")
            print(f"  SKIP: audio file not found: {audio_path}")
            results.append(StepResult(name="Voice (transcribe)", status="SKIP", error=f"File not found: {audio_path}"))
    else:
        print("\n--- 4. Muse Voice Transcribe ---")
        print("  SKIP: no --audio flag provided")
        results.append(StepResult(name="Voice (transcribe)", status="SKIP"))

    # Summary table
    print("=" * 80)
    print("SUMMARY")
    print_table(results)

    any_fail = any(r.status == "FAIL" for r in results)
    if any_fail:
        print("STATUS: PARTIAL FAILURE (see errors above)")
    else:
        ran = [r for r in results if r.status == "PASS"]
        print(f"STATUS: {'VERIFIED' if ran else 'NO STEPS RAN'} ({len(ran)} steps passed)")
    print("=" * 80)

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
