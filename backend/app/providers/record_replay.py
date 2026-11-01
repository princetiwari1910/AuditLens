"""Record/Replay wrapper for AuditLens AI providers.

Supports offline deterministic testing and reliable demonstrations:
- 'record' mode: executes the underlying provider call, saves serialized output
  to `data/fixtures/<hash>.json`.
- 'replay' mode: loads cached responses from `data/fixtures/<hash>.json` with zero network calls.
  Raises FileNotFoundError if the fixture is missing.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.providers.base import (
    Detection,
    SegmentDetection,
    Transcript,
    TranscriptSegment,
    TranscriptTurn,
)
from app.providers.client import (
    estimate_reasoner_cost,
    estimate_segmentation_cost,
    estimate_transcription_cost,
    execute_with_retry,
)
from app.providers.schemas import validate_verdict

logger = logging.getLogger("auditlens.providers.record_replay")


def _hash_input(data: Any) -> str:
    """Compute deterministic SHA256 hash for provider input."""
    if isinstance(data, (bytes, bytearray)):
        content = bytes(data)
    elif isinstance(data, (str, Path)):
        p = Path(data)
        if p.exists() and p.is_file():
            content = p.read_bytes()
        else:
            content = str(data).encode("utf-8")
    else:
        content = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:24]


def get_fixtures_dir() -> Path:
    settings = get_settings()
    fixtures_dir = settings.DATA_DIR / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return fixtures_dir


# ── Record/Replay Segmenter Wrapper ───────────────────────────────────────────

class RecordReplaySegmenter:
    """
    Wraps a Segmenter/SegmentationProvider in record or replay mode.
    """

    def __init__(self, inner: Any, mode: str = "replay") -> None:
        self.inner = inner
        self.mode = mode.lower()  # "record", "replay", or "passthrough"

    @property
    def scenario_hash(self) -> str:
        return getattr(self.inner, "scenario_hash", "record_replay")

    @property
    def version(self) -> str:
        return getattr(self.inner, "version", "1.0.0")

    def _get_hash(self, frame_paths: list[str], prompt: str) -> str:
        hashes = [_hash_input(p) for p in frame_paths]
        prompt_hash = hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()[:12]
        combined = f"seg:{prompt_hash}:{':'.join(hashes)}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:24]

    def find_objects(
        self,
        frame_paths: list[str],
        prompt: str,
        timestamps_s: list[float] | None = None,
    ) -> list[Detection]:
        fixture_hash = self._get_hash(frame_paths, prompt)
        fixtures_dir = get_fixtures_dir()
        fixture_file = fixtures_dir / f"{fixture_hash}.json"

        if self.mode == "replay":
            if not fixture_file.exists():
                raise FileNotFoundError(
                    f"[Replay Mode] Fixture '{fixture_hash}.json' missing in {fixtures_dir}. "
                    f"Zero network calls allowed in replay mode. Record the scenario first."
                )
            with open(fixture_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [
                Detection(
                    frame_id=d["frame_id"],
                    timestamp_s=d["timestamp_s"],
                    prompt=d["prompt"],
                    score=d["score"],
                    bbox=d["bbox"],
                    polygon=d.get("polygon"),
                )
                for d in data.get("detections", [])
            ]

        # Record or Passthrough mode: execute via hardened client with budget guard & retries
        cost = estimate_segmentation_cost(len(frame_paths))
        result = execute_with_retry(
            self.inner.find_objects,
            frame_paths,
            prompt,
            timestamps_s,
            estimated_cost=cost,
            is_video=False,
        )

        if self.mode == "record":
            serializable = {
                "hash": fixture_hash,
                "prompt": prompt,
                "detections": [asdict(d) for d in result],
            }
            with open(fixture_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
            logger.info("Recorded segmenter fixture to %s", fixture_file)

        return result

    def segment(
        self,
        image: str | bytes | Path,
        text_prompts: list[str],
    ) -> list[SegmentDetection]:
        img_hash = _hash_input(image)
        prompts_hash = hashlib.sha256(":".join(sorted(text_prompts)).encode("utf-8")).hexdigest()[:12]
        fixture_hash = f"segment_{img_hash[:12]}_{prompts_hash}"
        fixtures_dir = get_fixtures_dir()
        fixture_file = fixtures_dir / f"{fixture_hash}.json"

        if self.mode == "replay":
            if not fixture_file.exists():
                raise FileNotFoundError(
                    f"[Replay Mode] Fixture '{fixture_hash}.json' missing in {fixtures_dir}."
                )
            with open(fixture_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [
                SegmentDetection(
                    label=d["label"],
                    box=d["box"],
                    score=d["score"],
                    mask=d.get("mask"),
                    frame_id=d.get("frame_id", 0),
                    timestamp_s=d.get("timestamp_s", 0.0),
                )
                for d in data.get("detections", [])
            ]

        cost = estimate_segmentation_cost(1)

        def _call_segment() -> list[SegmentDetection]:
            if hasattr(self.inner, "segment"):
                return self.inner.segment(image, text_prompts)
            # Fallback using find_objects
            dets = []
            for p in text_prompts:
                sub = self.inner.find_objects([str(image)], p)
                for d in sub:
                    dets.append(
                        SegmentDetection(
                            label=d.prompt,
                            box=d.bbox,
                            score=d.score,
                            mask=d.polygon,
                            frame_id=d.frame_id,
                            timestamp_s=d.timestamp_s,
                        )
                    )
            return dets

        result = execute_with_retry(_call_segment, estimated_cost=cost, is_video=False)

        if self.mode == "record":
            serializable = {
                "hash": fixture_hash,
                "text_prompts": text_prompts,
                "detections": [asdict(d) for d in result],
            }
            with open(fixture_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)

        return result


# ── Record/Replay Transcriber Wrapper ─────────────────────────────────────────

class RecordReplayTranscriber:
    """
    Wraps a Transcriber/TranscriptionProvider in record or replay mode.
    """

    def __init__(self, inner: Any, mode: str = "replay") -> None:
        self.inner = inner
        self.mode = mode.lower()

    def transcribe(
        self,
        audio_path: str,
        language_hint: str | None = None,
    ) -> Transcript:
        audio_hash = _hash_input(audio_path)
        fixture_hash = f"trans_{audio_hash}"
        fixtures_dir = get_fixtures_dir()
        fixture_file = fixtures_dir / f"{fixture_hash}.json"

        if self.mode == "replay":
            if not fixture_file.exists():
                raise FileNotFoundError(
                    f"[Replay Mode] Transcript fixture '{fixture_hash}.json' missing in {fixtures_dir}. "
                    f"Zero network calls allowed in replay mode."
                )
            with open(fixture_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            segments = [
                TranscriptSegment(start_s=s["start_s"], end_s=s["end_s"], text=s["text"])
                for s in data.get("segments", [])
            ]
            turns = [
                TranscriptTurn(
                    start_s=t["start_s"],
                    end_s=t["end_s"],
                    text=t["text"],
                    speaker=t.get("speaker"),
                )
                for t in data.get("turns", [])
            ]
            return Transcript(
                text=data.get("text", ""),
                language=data.get("language", "en"),
                segments=segments,
                turns=turns,
            )

        # Record or Passthrough mode: execute via hardened client with budget guard & retries
        cost = estimate_transcription_cost(1.0)
        result = execute_with_retry(
            self.inner.transcribe,
            audio_path,
            language_hint=language_hint,
            estimated_cost=cost,
            is_video=False,
        )

        if self.mode == "record":
            turns_data = [asdict(t) for t in getattr(result, "turns", [])]
            segments_data = [asdict(s) for s in getattr(result, "segments", [])]
            serializable = {
                "hash": fixture_hash,
                "text": result.text,
                "language": result.language,
                "segments": segments_data,
                "turns": turns_data,
            }
            with open(fixture_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
            logger.info("Recorded transcriber fixture to %s", fixture_file)

        return result


# ── Record/Replay Reasoner Wrapper ────────────────────────────────────────────

class RecordReplayReasoner:
    """
    Wraps a Reasoner in record or replay mode.
    """

    def __init__(self, inner: Any, mode: str = "replay") -> None:
        self.inner = inner
        self.mode = mode.lower()

    def judge(
        self,
        rule: dict[str, Any] | Any,
        evidence: dict[str, Any] | list[Any],
    ) -> dict[str, Any]:
        rule_dict = rule if isinstance(rule, dict) else (rule.model_dump() if hasattr(rule, "model_dump") else asdict(rule))
        evidence_dict = evidence if isinstance(evidence, (dict, list)) else str(evidence)
        combined_hash = hashlib.sha256(
            json.dumps({"rule": rule_dict, "evidence": evidence_dict}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:24]

        fixture_hash = f"reason_{combined_hash}"
        fixtures_dir = get_fixtures_dir()
        fixture_file = fixtures_dir / f"{fixture_hash}.json"

        if self.mode == "replay":
            if not fixture_file.exists():
                raise FileNotFoundError(
                    f"[Replay Mode] Reasoner fixture '{fixture_hash}.json' missing in {fixtures_dir}."
                )
            with open(fixture_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return validate_verdict(data).to_dict()

        # Record or Passthrough mode: execute via hardened client with budget guard & retries
        cost = estimate_reasoner_cost()
        raw_result = execute_with_retry(
            self.inner.judge,
            rule,
            evidence,
            estimated_cost=cost,
            is_video=False,
        )
        validated_result = validate_verdict(raw_result).to_dict()

        if self.mode == "record":
            with open(fixture_file, "w", encoding="utf-8") as f:
                json.dump(validated_result, f, indent=2)
            logger.info("Recorded reasoner fixture to %s", fixture_file)

        return validated_result

    def verify_presence(
        self,
        concept: str,
        frames: list[dict[str, Any]] | list[str],
    ) -> dict[str, Any]:
        """Verify presence of a concept across frames with record/replay support."""
        from app.providers.schemas import validate_presence_verdict

        frame_ids: list[int] = []
        for i, f in enumerate(frames):
            if isinstance(f, dict):
                frame_ids.append(int(f.get("idx", f.get("id", i))))
            else:
                frame_ids.append(i)

        combined_hash = hashlib.sha256(
            json.dumps({"concept": concept, "frame_ids": frame_ids}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]

        fixture_hash = f"presence_{combined_hash}"
        fixtures_dir = get_fixtures_dir()
        fixture_file = fixtures_dir / f"{fixture_hash}.json"

        if self.mode == "replay":
            if not fixture_file.exists():
                if hasattr(self.inner, "verify_presence"):
                    return self.inner.verify_presence(concept, frames)
                return {
                    "present": False,
                    "cited_frame_ids": [],
                    "rationale": f"[Replay Mode] Presence fixture '{fixture_hash}.json' missing.",
                }
            with open(fixture_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return validate_presence_verdict(data, allowed_frame_ids=frame_ids)

        cost = estimate_reasoner_cost(0.5, 0.1)
        raw_result = execute_with_retry(
            self.inner.verify_presence,
            concept,
            frames,
            estimated_cost=cost,
            is_video=False,
        )
        validated_result = validate_presence_verdict(raw_result, allowed_frame_ids=frame_ids)

        if self.mode == "record":
            with open(fixture_file, "w", encoding="utf-8") as f:
                json.dump(validated_result, f, indent=2)
            logger.info("Recorded presence fixture to %s", fixture_file)

        return validated_result
