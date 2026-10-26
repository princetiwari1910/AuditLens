"""Deterministic mock implementations of AuditLens AI providers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any, Callable

from app.providers.base import (
    Detection,
    Transcript,
    TranscriptSegment,
    SegmentationProvider,
    TranscriptionProvider,
    AgentProvider,
)

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def _normalize_str(s: str) -> str:
    return s.strip().lower()


class MockSegmentationProvider:
    """
    Mock segmentation reading from demo_room.json when available.
    Falls back to deterministic pseudo-random detections seeded from (prompt, frame_index).
    Guarantees different prompts yield distinct detection outcomes.
    """

    def __init__(self, scenario_file: str | Path | None = None) -> None:
        self.scenario_path = (
            Path(scenario_file) if scenario_file else SCENARIOS_DIR / "demo_room.json"
        )
        self.scenario_items: list[dict[str, Any]] = []
        if self.scenario_path.exists():
            with open(self.scenario_path, "r", encoding="utf-8") as f:
                self.scenario_items = json.load(f)

    def _matches_scenario_item(self, prompt: str, item: dict[str, Any]) -> bool:
        norm_prompt = _normalize_str(prompt)
        item_prompt = _normalize_str(item.get("prompt", ""))
        if norm_prompt == item_prompt or norm_prompt in item_prompt or item_prompt in norm_prompt:
            return True
        for alias in item.get("aliases", []):
            norm_alias = _normalize_str(alias)
            if norm_prompt == norm_alias or norm_prompt in norm_alias or norm_alias in norm_prompt:
                return True
        return False

    def find_objects(
        self,
        frame_paths: list[str],
        prompt: str,
        timestamps_s: list[float] | None = None,
    ) -> list[Detection]:
        detections: list[Detection] = []
        norm_prompt = _normalize_str(prompt)

        matching_scenarios = [
            item for item in self.scenario_items if self._matches_scenario_item(prompt, item)
        ]

        for idx, path in enumerate(frame_paths):
            timestamp_s = (
                timestamps_s[idx] if timestamps_s and idx < len(timestamps_s) else float(idx)
            )

            if matching_scenarios:
                for item in matching_scenarios:
                    start_s = float(item.get("start_s", 0.0))
                    end_s = float(item.get("end_s", 9999.0))
                    if start_s <= timestamp_s <= end_s:
                        bbox = dict(item["bbox"])
                        poly = [list(pt) for pt in item.get("polygon", [])] if item.get("polygon") else None
                        detections.append(
                            Detection(
                                frame_id=idx,
                                timestamp_s=timestamp_s,
                                prompt=prompt,
                                score=float(item.get("score", 0.9)),
                                bbox=bbox,
                                polygon=poly,
                            )
                        )
            else:
                # Deterministic pseudo-random generation seeded strictly on (prompt, frame_idx)
                # This guarantees reproducibility and uniqueness across different prompts
                seed_str = f"auditlens_seed:{norm_prompt}:{idx}"
                seed_int = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
                rng = random.Random(seed_int)

                # Determine if an object is present in this frame (e.g. 35% probability)
                is_present = rng.random() < 0.35
                if is_present:
                    score = round(rng.uniform(0.35, 0.95), 3)
                    w = round(rng.uniform(0.08, 0.25), 3)
                    h = round(rng.uniform(0.08, 0.30), 3)
                    x = round(rng.uniform(0.05, 1.0 - w - 0.05), 3)
                    y = round(rng.uniform(0.10, 1.0 - h - 0.05), 3)
                    bbox = {"x": x, "y": y, "w": w, "h": h}
                    poly = [
                        [x, y],
                        [round(x + w, 3), y],
                        [round(x + w, 3), round(y + h, 3)],
                        [x, round(y + h, 3)],
                    ]
                    detections.append(
                        Detection(
                            frame_id=idx,
                            timestamp_s=timestamp_s,
                            prompt=prompt,
                            score=score,
                            bbox=bbox,
                            polygon=poly,
                        )
                    )

        return detections


class MockTranscriptionProvider:
    """
    Returns realistic Hinglish voice note transcriptions with timestamp segments.
    """

    def transcribe(
        self,
        audio_path: str,
        language_hint: str | None = None,
    ) -> Transcript:
        text = (
            "Main entrance ke paas fire extinguisher check kar liya hai, "
            "expiry date valid hai aur exit doorway ka rasta clear hai."
        )
        segments = [
            TranscriptSegment(
                start_s=0.0,
                end_s=3.2,
                text="Main entrance ke paas fire extinguisher check kar liya hai,",
            ),
            TranscriptSegment(
                start_s=3.3,
                end_s=6.8,
                text="expiry date valid hai aur exit doorway ka rasta clear hai.",
            ),
        ]
        return Transcript(
            text=text,
            language="hi-en",
            segments=segments,
        )


class MockAgentProvider:
    """
    Placeholder for AgentProvider protocol in mock mode (full runner is in agent/runner.py).
    """

    def run_audit(
        self,
        audit: Any,
        rules: list[Any],
        tools: Any,
        emit: Callable[[dict[str, Any]], None],
    ) -> list[Any]:
        # Handled by agent/runner.py in Milestone 4
        return []
