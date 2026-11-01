"""Deterministic mock implementations of AuditLens AI providers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any, Callable

from app.config import get_settings
from app.providers.base import (
    Detection,
    SegmentDetection,
    Transcript,
    TranscriptSegment,
    TranscriptTurn,
    SegmentationProvider,
    TranscriptionProvider,
    AgentProvider,
    Segmenter,
    Reasoner,
    Transcriber,
)
from app.providers.schemas import validate_verdict

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

    @property
    def version(self) -> str:
        return "mock-1.0"

    @property
    def scenario_hash(self) -> str:
        if self.scenario_path.exists():
            try:
                content = self.scenario_path.read_bytes()
                return hashlib.sha256(content).hexdigest()[:16]
            except Exception:
                pass
        return "none"

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

    def segment(
        self,
        image: str | bytes | Path,
        text_prompts: list[str],
    ) -> list[SegmentDetection]:
        """Implements Segmenter protocol using mock detection matching."""
        results: list[SegmentDetection] = []
        for p in text_prompts:
            dets = self.find_objects([str(image)], p)
            for d in dets:
                results.append(
                    SegmentDetection(
                        label=d.prompt,
                        box=d.bbox,
                        score=d.score,
                        mask=d.polygon,
                        frame_id=d.frame_id,
                        timestamp_s=d.timestamp_s,
                    )
                )
        return results


MockSegmenter = MockSegmentationProvider


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
            "[STUB / MOCK] Main entrance ke paas fire extinguisher check kar liya hai, "
            "expiry date valid hai aur exit doorway ka rasta clear hai."
        )
        segments = [
            TranscriptSegment(
                start_s=0.0,
                end_s=3.2,
                text="[STUB / MOCK] Main entrance ke paas fire extinguisher check kar liya hai,",
            ),
            TranscriptSegment(
                start_s=3.3,
                end_s=6.8,
                text="expiry date valid hai aur exit doorway ka rasta clear hai.",
            ),
        ]
        turns = [
            TranscriptTurn(
                start_s=0.0,
                end_s=3.2,
                text="[STUB / MOCK] Main entrance ke paas fire extinguisher check kar liya hai,",
                speaker="Auditor",
            ),
            TranscriptTurn(
                start_s=3.3,
                end_s=6.8,
                text="expiry date valid hai aur exit doorway ka rasta clear hai.",
                speaker="Auditor",
            ),
        ]
        return Transcript(
            text=text,
            language="hi-en",
            segments=segments,
            turns=turns,
        )


MockTranscriber = MockTranscriptionProvider


class MockReasoner:
    """Mock Reasoner evaluating safety rules against provided evidence."""

    def judge(
        self,
        rule: dict[str, Any] | Any,
        evidence: dict[str, Any] | list[Any],
    ) -> dict[str, Any]:
        rule_dict = rule if isinstance(rule, dict) else (rule.model_dump() if hasattr(rule, "model_dump") else {})
        r_type = rule_dict.get("type", "presence")
        r_title = rule_dict.get("title", "")

        # Deterministic verdict based on evidence contents
        cited_frames: list[int] = []
        if isinstance(evidence, list):
            for item in evidence:
                if isinstance(item, dict) and "frame_id" in item:
                    cited_frames.append(int(item["frame_id"]))
                elif hasattr(item, "frame_id"):
                    cited_frames.append(int(item.frame_id))

        if r_type == "absence":
            # If evidence has high-scoring obstacle -> fail
            has_obstacle = bool(evidence)
            raw = {
                "verdict": "fail" if has_obstacle else "pass",
                "status": "fail" if has_obstacle else "pass",
                "reason": f"Mock evaluation for {r_title}: {'Obstacle detected' if has_obstacle else 'No obstacles found'}.",
                "cited_frame_ids": cited_frames[:3],
                "confidence": 0.85 if has_obstacle else 0.90,
            }
        else:
            has_item = bool(evidence)
            raw = {
                "verdict": "pass" if has_item else "fail",
                "status": "pass" if has_item else "fail",
                "reason": f"Mock evaluation for {r_title}: {'Required item detected' if has_item else 'Item missing'}.",
                "cited_frame_ids": cited_frames[:3],
                "confidence": 0.88 if has_item else 0.40,
            }

        return validate_verdict(raw).to_dict()

    def verify_presence(
        self,
        concept: str,
        frames: list[dict[str, Any]] | list[str],
    ) -> dict[str, Any]:
        """Mock visual verification of a concept across frames."""
        from app.providers.schemas import validate_presence_verdict

        frame_ids: list[int] = []
        for i, f in enumerate(frames):
            if isinstance(f, dict):
                fid = f.get("idx", f.get("id", i))
                frame_ids.append(int(fid))
            else:
                frame_ids.append(i)

        clean_concept = concept.lower().strip()
        # Mock presence rule: positive for known scenario objects
        known_positive = ["fire extinguisher", "extinguisher", "exit sign", "emergency exit", "safety helmet", "first aid", "person"]
        is_present = any(kp in clean_concept for kp in known_positive) and bool(frame_ids)

        settings = get_settings()
        cascade_enabled = getattr(settings, "ENABLE_ESCALATION_CASCADE", False)
        esc_model = getattr(settings, "ESCALATION_MODEL", None)
        if cascade_enabled and esc_model:
            if "-contributor" in esc_model.lower():
                raise ValueError(
                    f"Model ID '{esc_model}' rejected: '-contributor' models train on user content. "
                    "Only Standard mode models are permitted."
                )
            if not is_present and "escalate" in clean_concept:
                is_present = True

        cited = frame_ids[:2] if is_present else []
        rationale = (
            f"[MOCK] Visual inspection verified '{clean_concept}' in cited frames."
            if is_present
            else f"[MOCK] Visual inspection did not identify '{clean_concept}' in the provided frames."
        )
        if cascade_enabled and esc_model and "escalate" in clean_concept:
            rationale += f" [MOCK: Escalated to {esc_model}]"

        return validate_presence_verdict(
            {"present": is_present, "cited_frame_ids": cited, "rationale": rationale},
            allowed_frame_ids=frame_ids,
        )

    def plan_fixes(
        self,
        findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Generate deterministic prioritized fix actions grounded in findings."""
        from app.providers.schemas import validate_fix_actions

        # Target non-pass findings or findings requiring action
        eligible = [
            f for f in findings
            if f.get("status") in ("fail", "unsure") or f.get("final_verdict") in ("fail", "unsure")
        ]

        # Prioritize: fail before unsure; high before medium before low
        sev_rank = {"high": 0, "medium": 1, "low": 2}

        def _sort_key(f: dict[str, Any]) -> tuple[int, int]:
            st = f.get("final_verdict") or f.get("status") or "unsure"
            status_order = 0 if st == "fail" else 1
            severity_order = sev_rank.get(f.get("severity", "medium").lower(), 1)
            return (status_order, severity_order)

        sorted_findings = sorted(eligible, key=_sort_key)
        actions: list[dict[str, Any]] = []

        for f in sorted_findings:
            f_id = f.get("id", "")
            rule_id = f.get("rule_id", "")
            severity = f.get("severity", "medium").lower()
            fix_text = f.get("fix_text", "").strip()

            if not fix_text:
                if "path" in rule_id or "exit" in rule_id and "block" in rule_id:
                    fix_text = "Clear all boxes and obstructions immediately to restore egress path width."
                elif "extinguisher" in rule_id:
                    fix_text = "Mount inspected and certified extinguisher in designated unobstructed location."
                elif "sign" in rule_id:
                    fix_text = "Install high-visibility illuminated exit sign above emergency door."
                else:
                    fix_text = f"Address {rule_id} deficiency and perform follow-up safety verification."

            fix_lower = fix_text.lower()
            if any(k in fix_lower for k in ["clear", "box", "remove", "trash", "aisle"]):
                effort = "S"
                due_days = 2
            elif any(k in fix_lower for k in ["extinguisher", "sign", "mount", "tag", "inspect"]):
                effort = "M"
                due_days = 7
            elif any(k in fix_lower for k in ["door", "width", "structural", "construct", "ramp"]):
                effort = "L"
                due_days = 30
            else:
                if severity == "high":
                    effort = "M"
                    due_days = 3
                elif severity == "medium":
                    effort = "M"
                    due_days = 7
                else:
                    effort = "S"
                    due_days = 14

            actions.append({
                "finding_id": f_id,
                "rule_id": rule_id,
                "severity": severity,
                "effort": effort,
                "suggested_fix": fix_text,
                "suggested_due_days": due_days,
                "label": "AI-suggested (MOCK)",
            })

        allowed_ids = [f.get("id") for f in findings if f.get("id")]
        return validate_fix_actions(actions, allowed_finding_ids=allowed_ids)

    def compile_template(
        self,
        text: str,
    ) -> dict[str, Any]:
        """Compile natural language safety checklist text into draft template JSON."""
        import re
        import uuid

        lines = [line.strip().lstrip("-*123456789. ") for line in text.splitlines() if line.strip()]
        if not lines:
            lines = [text.strip()] if text.strip() else ["Check general safety"]

        rules: list[dict[str, Any]] = []
        for idx, line in enumerate(lines):
            line_lower = line.lower()
            rule_id = f"rule_{idx + 1}"
            r_type = "presence"
            prompts: list[str] = []

            # Check if user intentionally provided a raw prompt with commas, conjunctions, or spatial words
            if "prompt:" in line_lower:
                raw_p = line.split("prompt:", 1)[1].strip()
                prompts = [raw_p]
            elif "concept:" in line_lower:
                raw_p = line.split("concept:", 1)[1].strip()
                prompts = [raw_p]
            elif '"' in line:
                quotes = re.findall(r'"([^"]*)"', line)
                if quotes:
                    prompts = quotes
            elif "'" in line:
                quotes = re.findall(r"'([^']*)'", line)
                if quotes:
                    prompts = quotes

            if not prompts:
                if "extinguisher" in line_lower:
                    rule_id = f"custom_extinguisher_{idx + 1}"
                    prompts = ["fire extinguisher"]
                    r_type = "presence"
                elif "sign" in line_lower:
                    rule_id = f"custom_exit_sign_{idx + 1}"
                    prompts = ["exit sign"]
                    r_type = "presence"
                elif any(k in line_lower for k in ["clear", "block", "obstacle", "pallet", "box"]):
                    rule_id = f"custom_unblocked_{idx + 1}"
                    prompts = ["box"]
                    r_type = "absence"
                elif "helmet" in line_lower or "ppe" in line_lower:
                    rule_id = f"custom_ppe_{idx + 1}"
                    prompts = ["safety helmet"]
                    r_type = "presence"
                else:
                    clean_title = re.sub(
                        r"^(check|ensure|verify|inspect|make sure|look for)\s+",
                        "",
                        line,
                        flags=re.IGNORECASE,
                    ).strip()
                    rule_id = f"custom_item_{idx + 1}"
                    prompts = [clean_title if clean_title else "safety equipment"]

            rules.append({
                "id": rule_id,
                "title": line[:60],
                "type": r_type,
                "severity": "high" if any(w in line_lower for w in ["fire", "hazard", "danger", "critical"]) else "medium",
                "sam_prompts": prompts,
                "detector": "sam",
                "fix_text": f"Remediate {line[:60]} requirement.",
            })

        slug = f"custom_compiled_{uuid.uuid4().hex[:6]}"
        return {
            "id": slug,
            "name": "Custom Compiled Checklist (Experimental)",
            "description": "Compiled from natural language instructions. Human-reviewed.",
            "status": "experimental",
            "human_reviewed": True,
            "rules": rules,
        }

    def extract_note(
        self,
        transcript: str,
    ) -> dict[str, Any]:
        """Extract structured {location, issue, severity_hint} from spoken transcript, supporting Hinglish."""
        from app.providers.schemas import validate_structured_voice_note

        t_lower = transcript.lower()

        # Location extraction (English and Hindi/Hinglish terms)
        location = "General Area"
        if any(w in t_lower for w in ["entrance", "entry", "gate", "doorway", "darwaza", "main gate"]):
            location = "Main Entrance"
        elif any(w in t_lower for w in ["hallway", "corridor", "rasta", "aisle", "passage", "walkway"]):
            location = "Hallway / Egress Path"
        elif any(w in t_lower for w in ["exit", "fire door", "emergency exit", "stair", "stairs"]):
            location = "Emergency Exit Door"
        elif any(w in t_lower for w in ["lab", "room", "workshop", "kamra", "office"]):
            location = "Work Area"

        # Severity hint
        severity = "medium"
        if any(w in t_lower for w in ["danger", "hazard", "khatra", "emergency", "critical", "blocked", "band", "expire", "fail", "bad"]):
            severity = "high"
        elif any(w in t_lower for w in ["minor", "slight", "theek", "clear", "pass", "ok", "valid", "saaf", "good"]):
            severity = "low"

        # Issue extraction
        issue = transcript.strip()
        if "fire extinguisher" in t_lower or "extinguisher" in t_lower:
            if "expire" in t_lower or "check" in t_lower or "valid" in t_lower:
                issue = "Fire extinguisher inspection & validity check"
            else:
                issue = "Fire extinguisher condition observation"
        elif "exit" in t_lower or "rasta" in t_lower or "door" in t_lower:
            if "block" in t_lower or "band" in t_lower or "box" in t_lower:
                issue = "Exit obstruction / blockage reported"
            else:
                issue = "Exit path clearance check"

        raw = {
            "location": location,
            "issue": issue,
            "severity_hint": severity,
            "raw_transcript": transcript,
        }
        return validate_structured_voice_note(raw)





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
