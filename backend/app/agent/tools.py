"""Plain Python tools with JSON Schemas and Evidence-First enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
import uuid
from typing import Any, Callable

from sqlmodel import Session

from app.agent.measure import compute_pixels_per_meter, estimate_clear_width
from app.agent.rules import compute_bbox_overlap
from app.cache import compute_cache_key, get_cached_result, set_cached_result
from app.costlog import log_cost
from app.models import FindingStatus, RuleModel


class EvidenceError(ValueError):
    """Raised when record_finding violates Evidence-First rules."""
    pass


@dataclass
class EvidenceEntry:
    result_id: str
    tool_name: str
    args: dict[str, Any]
    data: Any


class ExecutionContext:
    """Audit runtime state tracking registered evidence results."""

    def __init__(
        self,
        audit_id: str,
        rules: list[RuleModel],
        frames: list[dict[str, Any]],
        segmentation_provider: Any,
        transcription_provider: Any,
        voice_notes: list[dict[str, Any]] | None = None,
        session: Session | None = None,
        reasoner: Any | None = None,
    ) -> None:
        self.audit_id = audit_id
        self.rules = rules
        self.frames = frames  # list of {"idx": i, "timestamp_s": t, "path": p, "sha256": s}
        self.segmentation_provider = segmentation_provider
        self.transcription_provider = transcription_provider
        self.voice_notes = voice_notes or []
        self.session = session
        self.reasoner = reasoner

        # Evidence store: maps result_id -> EvidenceEntry
        self.evidence_store: dict[str, EvidenceEntry] = {}
        # Findings recorded during execution
        self.findings: list[dict[str, Any]] = []

    def register_evidence(self, tool_name: str, args: dict[str, Any], data: Any) -> str:
        res_id = f"res_{uuid.uuid4().hex[:12]}"
        self.evidence_store[res_id] = EvidenceEntry(
            result_id=res_id,
            tool_name=tool_name,
            args=args,
            data=data,
        )
        return res_id


class ToolRegistry:
    """Registry exposing tool JSON Schemas and dispatching calls."""

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx
        self._tools: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {}
        self._register_all()

    def _register_all(self) -> None:
        self.register(
            "list_rules",
            self.list_rules,
            {
                "type": "function",
                "function": {
                    "name": "list_rules",
                    "description": "List all safety checklist rules assigned to the current audit.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        )
        self.register(
            "find_objects",
            self.find_objects,
            {
                "type": "function",
                "function": {
                    "name": "find_objects",
                    "description": "Ground and segment target objects across sampled frames using visual models.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "frame_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Specific frame indexes to scan (or empty for all).",
                            },
                            "prompt": {
                                "type": "string",
                                "description": "Text description of the object to detect.",
                            },
                            "min_score": {
                                "type": "number",
                                "description": "Minimum confidence threshold (0.0 to 1.0).",
                            },
                        },
                        "required": ["prompt"],
                    },
                },
            },
        )
        self.register(
            "check_colocation",
            self.check_colocation,
            {
                "type": "function",
                "function": {
                    "name": "check_colocation",
                    "description": "Verify spatial co-location and overlap between a container object and an item.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "frame_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Frame indexes to inspect.",
                            },
                            "container_prompt": {
                                "type": "string",
                                "description": "Description of container object (e.g. 'person').",
                            },
                            "item_prompt": {
                                "type": "string",
                                "description": "Description of required item (e.g. 'safety helmet').",
                            },
                            "min_overlap": {
                                "type": "number",
                                "description": "Minimum intersection ratio (0.0 to 1.0).",
                            },
                        },
                        "required": ["container_prompt", "item_prompt"],
                    },
                },
            },
        )
        self.register(
            "measure_clear_width",
            self.measure_clear_width,
            {
                "type": "function",
                "function": {
                    "name": "measure_clear_width",
                    "description": "Estimate horizontal clear walkway bottleneck width at floor level with uncertainty.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "frame_id": {
                                "type": "integer",
                                "description": "Frame index containing the corridor bottleneck.",
                            },
                            "obstacle_prompts": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of obstacle descriptions to locate and measure between.",
                            },
                            "reference": {
                                "type": "object",
                                "description": "Scale reference specification (e.g. {'type': 'a4'}).",
                            },
                        },
                        "required": ["obstacle_prompts"],
                    },
                },
            },
        )
        self.register(
            "get_voice_notes",
            self.get_voice_notes,
            {
                "type": "function",
                "function": {
                    "name": "get_voice_notes",
                    "description": "Retrieve transcribed auditor voice notes recorded near a specific timestamp.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rule_id": {"type": "string"},
                            "near_timestamp_s": {"type": "number"},
                        },
                    },
                },
            },
        )
        self.register(
            "verify_presence",
            self.verify_presence,
            {
                "type": "function",
                "function": {
                    "name": "verify_presence",
                    "description": "Active visual verification of concept across keyframes using Muse Spark Reasoner.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "concept": {"type": "string"},
                            "frame_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Optional subset of frame IDs to inspect.",
                            },
                        },
                        "required": ["concept"],
                    },
                },
            },
        )
        self.register(
            "record_finding",
            self.record_finding,
            {
                "type": "function",
                "function": {
                    "name": "record_finding",
                    "description": "Record an evidence-backed audit finding. Strictly enforces evidence validation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rule_id": {"type": "string"},
                            "status": {"type": "string", "enum": ["pass", "fail", "unsure"]},
                            "confidence": {"type": "number"},
                            "frame_id": {"type": "integer"},
                            "timestamp_s": {"type": "number"},
                            "evidence_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of valid result_ids produced earlier during this audit.",
                            },
                            "measurement": {"type": "object"},
                            "rationale": {"type": "string"},
                            "severity": {"type": "string"},
                            "sources": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["rule_id", "status", "confidence", "evidence_ids"],
                    },
                },
            },
        )

    def register(self, name: str, fn: Callable[..., Any], schema: dict[str, Any]) -> None:
        self._tools[name] = (fn, schema)

    def get_schemas(self) -> list[dict[str, Any]]:
        return [schema for _, schema in self._tools.values()]

    def execute(self, tool_name: str, **kwargs) -> dict[str, Any]:
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: '{tool_name}'")
        fn, _ = self._tools[tool_name]
        return fn(**kwargs)

    # ── Tool Implementations ──────────────────────────────────────────────────

    def list_rules(self) -> dict[str, Any]:
        rules_data = [r.model_dump() for r in self.ctx.rules]
        res_id = self.ctx.register_evidence("list_rules", {}, rules_data)
        return {"result_id": res_id, "rules": rules_data}

    def find_objects(
        self,
        prompt: str,
        frame_ids: list[int] | None = None,
        min_score: float = 0.0,
    ) -> dict[str, Any]:
        if frame_ids:
            selected_frames = [f for f in self.ctx.frames if f["idx"] in frame_ids]
        else:
            selected_frames = self.ctx.frames

        detections: list[dict[str, Any]] = []
        frames_to_query: list[dict[str, Any]] = []
        frame_cache_keys: dict[int, str] = {}

        # 1. Check Cache
        session = self.ctx.session
        provider = self.ctx.segmentation_provider
        provider_name = "segmentation"
        provider_version = getattr(provider, "version", "1.0.0")
        scenario_hash = getattr(provider, "scenario_hash", "")

        cached_hits_count = 0
        for f in selected_frames:
            f_idx = f["idx"]
            f_hash = f.get("sha256", str(f_idx))
            ckey = compute_cache_key(
                f_hash,
                provider_name,
                prompt,
                provider_version=provider_version,
                scenario_hash=scenario_hash,
            )
            frame_cache_keys[f_idx] = ckey

            cached_data = None
            if session is not None:
                cached_data = get_cached_result(session, ckey)

            if cached_data is not None:
                cached_hits_count += 1
                for d in cached_data:
                    if d.get("score", 0.0) >= min_score:
                        detections.append(d)
            else:
                frames_to_query.append(f)

        if session is not None and cached_hits_count > 0:
            log_cost(
                session,
                provider="segmentation",
                operation="segmentation",
                units=0.0,
                audit_id=self.ctx.audit_id,
                latency_ms=1,
                cache_hit=True,
            )

        # 2. Query provider for cache misses
        if frames_to_query:
            query_paths = [f["path"] for f in frames_to_query]
            query_timestamps = [f["timestamp_s"] for f in frames_to_query]

            t0 = time.time()
            raw_detections = self.ctx.segmentation_provider.find_objects(
                frame_paths=query_paths,
                prompt=prompt,
                timestamps_s=query_timestamps,
            )
            latency_ms = max(int((time.time() - t0) * 1000), 5)

            # Log provider cost
            if session is not None:
                log_cost(
                    session,
                    provider="segmentation",
                    operation="segmentation",
                    units=float(len(frames_to_query)),
                    audit_id=self.ctx.audit_id,
                    latency_ms=latency_ms,
                    cache_hit=False,
                )

            # Group new detections by frame index and cache
            by_frame: dict[int, list[dict[str, Any]]] = {f["idx"]: [] for f in frames_to_query}
            for d in raw_detections:
                target_f = frames_to_query[d.frame_id] if d.frame_id < len(frames_to_query) else frames_to_query[0]
                det_dict = {
                    "frame_id": target_f["idx"],
                    "timestamp_s": d.timestamp_s,
                    "prompt": d.prompt,
                    "score": d.score,
                    "bbox": d.bbox,
                    "polygon": d.polygon,
                }
                by_frame[target_f["idx"]].append(det_dict)
                if d.score >= min_score:
                    detections.append(det_dict)

            # Store in cache
            if session is not None:
                for f in frames_to_query:
                    f_idx = f["idx"]
                    ckey = frame_cache_keys[f_idx]
                    set_cached_result(session, ckey, "segmentation", prompt, by_frame[f_idx])

        res_id = self.ctx.register_evidence(
            "find_objects",
            {"prompt": prompt, "frame_ids": frame_ids, "min_score": min_score},
            detections,
        )
        return {
            "result_id": res_id,
            "prompt": prompt,
            "count": len(detections),
            "detections": detections,
        }

    def check_colocation(
        self,
        container_prompt: str,
        item_prompt: str,
        frame_ids: list[int] | None = None,
        min_overlap: float = 0.20,
    ) -> dict[str, Any]:
        containers_res = self.find_objects(prompt=container_prompt, frame_ids=frame_ids)
        items_res = self.find_objects(prompt=item_prompt, frame_ids=frame_ids)

        containers = containers_res["detections"]
        items = items_res["detections"]

        matches = []
        for c in containers:
            c_box = c["bbox"]
            c_time = c["timestamp_s"]
            matching_items = [
                it for it in items
                if abs(it["timestamp_s"] - c_time) <= 1.5
            ]
            for it in matching_items:
                overlap = compute_bbox_overlap(c_box, it["bbox"])
                if overlap >= min_overlap:
                    matches.append({
                        "container": c,
                        "item": it,
                        "overlap": round(overlap, 3),
                    })

        res_id = self.ctx.register_evidence(
            "check_colocation",
            {"container_prompt": container_prompt, "item_prompt": item_prompt, "min_overlap": min_overlap},
            {"containers": containers, "items": items, "matches": matches},
        )
        return {
            "result_id": res_id,
            "containers_count": len(containers),
            "items_count": len(items),
            "matches": matches,
            "containers": containers,
            "items": items,
        }

    def measure_clear_width(
        self,
        obstacle_prompts: list[str],
        frame_id: int | None = None,
        reference: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ref = reference or {"type": "a4"}

        # 1. Calibrate scale using optical reference
        ref_dets: list[dict[str, Any]] = []
        if ref.get("type") == "a4":
            a4_res = self.find_objects(prompt="a4", frame_ids=[frame_id] if frame_id is not None else None)
            ref_dets = a4_res["detections"]

        chosen_ref_det = ref_dets[0] if ref_dets else None
        ppm, cal_method = compute_pixels_per_meter(
            reference=ref,
            frame_width_px=1280,
            frame_height_px=720,
            reference_detection=chosen_ref_det,
        )

        # 2. Locate obstacles
        all_obstacles = []
        target_fids = [frame_id] if frame_id is not None else None
        for p in obstacle_prompts:
            obs_res = self.find_objects(prompt=p, frame_ids=target_fids)
            all_obstacles.extend(obs_res["detections"])

        obstacle_boxes = [o["bbox"] for o in all_obstacles]

        meas = estimate_clear_width(
            obstacle_boxes=obstacle_boxes,
            frame_width_px=1280,
            frame_height_px=720,
            pixels_per_meter=ppm,
            method=cal_method,
        )

        data = meas.to_dict()
        res_id = self.ctx.register_evidence(
            "measure_clear_width",
            {"obstacle_prompts": obstacle_prompts, "frame_id": frame_id, "reference": ref},
            data,
        )
        data["result_id"] = res_id
        return data

    def get_voice_notes(
        self,
        rule_id: str | None = None,
        near_timestamp_s: float | None = None,
    ) -> dict[str, Any]:
        notes = self.ctx.voice_notes
        if near_timestamp_s is not None and notes:
            # Sort by proximity to timestamp
            notes = sorted(notes, key=lambda n: abs(float(n.get("timestamp_s", 0.0)) - near_timestamp_s))
            notes = notes[:2]  # Closest 2 notes

        res_id = self.ctx.register_evidence(
            "get_voice_notes",
            {"rule_id": rule_id, "near_timestamp_s": near_timestamp_s},
            notes,
        )
        return {"result_id": res_id, "notes": notes}

    def verify_presence(
        self,
        concept: str,
        frame_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Verify presence of a concept using Reasoner vision capabilities."""
        frames_to_query = self.ctx.frames
        if frame_ids is not None:
            fset = set(frame_ids)
            frames_to_query = [f for f in self.ctx.frames if f["idx"] in fset]
        if not frames_to_query and self.ctx.frames:
            frames_to_query = self.ctx.frames[:4]

        reasoner = getattr(self.ctx, "reasoner", None)
        if reasoner is None:
            from app.providers import get_reasoner
            reasoner = get_reasoner()

        t0 = time.time()
        res = reasoner.verify_presence(concept, frames_to_query)
        latency_ms = max(int((time.time() - t0) * 1000), 5)

        session = self.ctx.session
        if session is not None:
            log_cost(
                session,
                provider="agent",
                operation="verify_presence",
                units=float(len(frames_to_query)) * 0.25,
                audit_id=self.ctx.audit_id,
                latency_ms=latency_ms,
                cache_hit=False,
            )

        res_id = self.ctx.register_evidence(
            "verify_presence",
            {"concept": concept, "frame_ids": [f["idx"] for f in frames_to_query]},
            res,
        )
        return {
            "result_id": res_id,
            "present": res.get("present", False),
            "cited_frame_ids": res.get("cited_frame_ids", []),
            "rationale": res.get("rationale", ""),
        }

    def record_finding(
        self,
        rule_id: str,
        status: str,
        confidence: float,
        evidence_ids: list[str],
        frame_id: int = 0,
        timestamp_s: float = 0.0,
        measurement: dict[str, Any] | None = None,
        rationale: str = "",
        severity: str = "medium",
        sources: list[str] | None = None,
        fix_text: str = "",
        evidence_ledger: list[dict[str, Any]] | None = None,
        strongest_evidence: dict[str, Any] | None = None,
        decision_policy: str = "default",
        detector: str = "sam",
        support_count: int = 1,
        stability: float = 1.0,
        escalation_steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Record finding with strict Evidence-First validation.
        """
        # ── EVIDENCE-FIRST ENFORCEMENT ─────────────────────────────────────────
        if not evidence_ids:
            # No evidence referenced at all -> MUST force status to 'unsure'
            status = FindingStatus.UNSURE.value
            rationale = "Unsure: no supporting visual evidence or measurement provided for evaluation."
            confidence = 0.0
        else:
            # Validate every referenced evidence_id exists in our execution store
            for eid in evidence_ids:
                if eid not in self.ctx.evidence_store:
                    raise EvidenceError(
                        f"Evidence validation failed: result_id '{eid}' was not produced during this audit execution."
                    )

            # Check if any evidence actually contained detections or measurements
            has_factual_content = False
            for eid in evidence_ids:
                entry = self.ctx.evidence_store[eid]
                if entry.tool_name == "find_objects" and len(entry.data) > 0:
                    has_factual_content = True
                elif entry.tool_name == "measure_clear_width" and "width_m" in entry.data:
                    has_factual_content = True
                elif entry.tool_name == "check_colocation":
                    has_factual_content = True
                elif entry.tool_name == "verify_presence" and entry.data.get("present"):
                    has_factual_content = True
                elif entry.tool_name == "list_rules":
                    # list_rules alone is not visual evidence
                    pass

            # If evidence references only yielded empty detection sets and claimed pass/fail
            if not has_factual_content and status == FindingStatus.PASS.value:
                # Absence rules can pass with 0 detections, but presence/measurement cannot
                rule = next((r for r in self.ctx.rules if r.id == rule_id), None)
                if rule and rule.type != "absence":
                    status = FindingStatus.UNSURE.value
                    rationale = f"Unsure: rule '{rule_id}' has no matching detections to substantiate compliance."
                    confidence = 0.0

        finding_id = f"f_{uuid.uuid4().hex[:8]}"
        finding = {
            "id": finding_id,
            "audit_id": self.ctx.audit_id,
            "rule_id": rule_id,
            "status": status,
            "confidence": round(confidence, 2),
            "frame_idx": frame_id,
            "timestamp_s": round(timestamp_s, 2),
            "measurement": measurement,
            "rationale": rationale,
            "fix_text": fix_text,
            "severity": severity,
            "sources": sources or ["segmentation"],
            "evidence_ids": evidence_ids,
            "evidence_ledger": evidence_ledger or [],
            "strongest_evidence": strongest_evidence,
            "decision_policy": decision_policy,
            "detector": detector,
            "support_count": support_count,
            "stability": stability,
            "escalation_steps": escalation_steps or [],
        }
        self.ctx.findings.append(finding)
        return {"finding_id": finding_id, "finding": finding}
