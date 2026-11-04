"""Tests for Meta structured-output schema compliance and reasoning effort config.

Tests items 1-3 from the live API fix:
1. All JSON schemas comply with dev.meta.ai/docs/structured-output rules
2. Reasoning effort config (SPARK_REASONING_EFFORT) works correctly
3. smoke_meta.py structure (independent steps, concepts validation)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.providers.schemas import (
    ALL_SPARK_SCHEMAS,
    SPARK_FIX_PLAN_JSON_SCHEMA,
    SPARK_NOTE_EXTRACTION_JSON_SCHEMA,
    SPARK_PRESENCE_JSON_SCHEMA,
    SPARK_TEMPLATE_DRAFT_JSON_SCHEMA,
    SPARK_VERDICT_JSON_SCHEMA,
    compute_schema_depth,
    validate_meta_schema_compliance,
)


# ── Item 1: Schema Compliance ─────────────────────────────────────────────────


class TestMetaSchemaCompliance:
    """Walk ALL_SPARK_SCHEMAS and assert Meta structured-output rules."""

    @pytest.mark.parametrize("name,schema", list(ALL_SPARK_SCHEMAS.items()))
    def test_schema_compliance(self, name: str, schema: dict) -> None:
        """Every registered schema must pass Meta structured-output compliance."""
        errors = validate_meta_schema_compliance(schema)
        assert errors == [], f"Schema '{name}' has compliance violations:\n" + "\n".join(errors)

    @pytest.mark.parametrize("name,schema", list(ALL_SPARK_SCHEMAS.items()))
    def test_additionalProperties_false_everywhere(self, name: str, schema: dict) -> None:
        """Every object node must have additionalProperties: false."""
        self._walk_objects(schema, name)

    def _walk_objects(self, node: dict, path: str) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, (
                f"{path}: missing additionalProperties: false"
            )
        for key, val in node.items():
            if isinstance(val, dict):
                self._walk_objects(val, f"{path}.{key}")
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, dict):
                        self._walk_objects(item, f"{path}.{key}[{i}]")

    @pytest.mark.parametrize("name,schema", list(ALL_SPARK_SCHEMAS.items()))
    def test_all_properties_in_required(self, name: str, schema: dict) -> None:
        """Every property defined must appear in required."""
        self._walk_required(schema, name)

    def _walk_required(self, node: dict, path: str) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            props = set(node.get("properties", {}).keys())
            required = set(node.get("required", []))
            missing = props - required
            assert not missing, (
                f"{path}: properties {sorted(missing)} not in required"
            )
        for key, val in node.items():
            if isinstance(val, dict):
                self._walk_required(val, f"{path}.{key}")
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, dict):
                        self._walk_required(item, f"{path}.{key}[{i}]")

    @pytest.mark.parametrize("name,schema", list(ALL_SPARK_SCHEMAS.items()))
    def test_nesting_depth_within_limit(self, name: str, schema: dict) -> None:
        """Schema nesting depth must be <= 3."""
        depth = compute_schema_depth(schema)
        assert depth <= 3, f"Schema '{name}' depth {depth} exceeds 3"

    @pytest.mark.parametrize("name,schema", list(ALL_SPARK_SCHEMAS.items()))
    def test_no_unsupported_keywords(self, name: str, schema: dict) -> None:
        """No unsupported keywords like $schema, title, description, minimum, maximum."""
        unsupported = {
            "$schema", "title", "description", "default",
            "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
            "minLength", "maxLength", "pattern", "minItems", "maxItems",
            "uniqueItems", "$ref", "$defs", "definitions",
            "if", "then", "else", "allOf", "anyOf", "oneOf", "not",
        }
        self._walk_keywords(schema, name, unsupported)

    def _walk_keywords(self, node: dict, path: str, unsupported: set[str]) -> None:
        if not isinstance(node, dict):
            return
        for key in node:
            assert key not in unsupported, (
                f"{path}: unsupported keyword '{key}'"
            )
        for key, val in node.items():
            if key == "properties" and isinstance(val, dict):
                # Inspect property schemas, not the property names themselves
                for prop_name, prop_schema in val.items():
                    if isinstance(prop_schema, dict):
                        self._walk_keywords(prop_schema, f"{path}.properties.{prop_name}", unsupported)
            elif isinstance(val, dict):
                self._walk_keywords(val, f"{path}.{key}", unsupported)
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, dict):
                        self._walk_keywords(item, f"{path}.{key}[{i}]", unsupported)

    @pytest.mark.parametrize("name,schema", list(ALL_SPARK_SCHEMAS.items()))
    def test_no_recursive_refs(self, name: str, schema: dict) -> None:
        """No $ref in any schema."""
        assert "$ref" not in json.dumps(schema), f"Schema '{name}' contains $ref"

    def test_verdict_schema_has_all_fields_required(self) -> None:
        """Verdict schema: status, reason, cited_frame_ids, confidence all required."""
        required = set(SPARK_VERDICT_JSON_SCHEMA["required"])
        expected = {"status", "reason", "cited_frame_ids", "confidence"}
        assert required == expected

    def test_presence_schema_structure(self) -> None:
        """Presence schema: present, cited_frame_ids, rationale all required."""
        required = set(SPARK_PRESENCE_JSON_SCHEMA["required"])
        assert required == {"present", "cited_frame_ids", "rationale"}

    def test_fix_plan_schema_structure(self) -> None:
        """Fix plan schema: actions array with nested object."""
        assert "actions" in SPARK_FIX_PLAN_JSON_SCHEMA["properties"]
        items = SPARK_FIX_PLAN_JSON_SCHEMA["properties"]["actions"]["items"]
        assert items["additionalProperties"] is False
        assert set(items["required"]) == {
            "finding_id", "rule_id", "severity", "effort", "suggested_fix", "suggested_due_days"
        }

    def test_note_extraction_schema_structure(self) -> None:
        """Note extraction schema: location, issue, severity_hint, raw_transcript."""
        required = set(SPARK_NOTE_EXTRACTION_JSON_SCHEMA["required"])
        assert required == {"location", "issue", "severity_hint", "raw_transcript"}

    def test_template_draft_schema_structure(self) -> None:
        """Template draft schema: name and rules array."""
        required = set(SPARK_TEMPLATE_DRAFT_JSON_SCHEMA["required"])
        assert required == {"name", "rules"}
        items = SPARK_TEMPLATE_DRAFT_JSON_SCHEMA["properties"]["rules"]["items"]
        assert items["additionalProperties"] is False

    def test_compliance_validator_catches_additionalProperties_true(self) -> None:
        """validate_meta_schema_compliance catches additionalProperties: true."""
        bad = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": True}
        errors = validate_meta_schema_compliance(bad)
        assert any("additionalProperties" in e for e in errors)

    def test_compliance_validator_catches_missing_required(self) -> None:
        """validate_meta_schema_compliance catches properties not in required."""
        bad = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}, "required": ["a"], "additionalProperties": False}
        errors = validate_meta_schema_compliance(bad)
        assert any("not listed in required" in e for e in errors)

    def test_compliance_validator_catches_unsupported_keyword(self) -> None:
        """validate_meta_schema_compliance catches $schema, title, description, etc."""
        bad = {"$schema": "...", "type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": False}
        errors = validate_meta_schema_compliance(bad)
        assert any("$schema" in e for e in errors)


# ── Item 2: Reasoning Effort ──────────────────────────────────────────────────


class TestReasoningEffort:
    """Test reasoning effort configuration for MetaAgentProvider."""

    def test_default_reasoning_effort_is_low(self) -> None:
        """Default SPARK_REASONING_EFFORT is 'low'."""
        s = Settings(MODEL_API_KEY="", META_API_KEY="")
        assert s.SPARK_REASONING_EFFORT == "low"

    def test_high_effort_for_complex_calls(self) -> None:
        """SPARK_REASONING_EFFORT_HIGH defaults to 'high' for fix_plan/compile_template."""
        s = Settings(MODEL_API_KEY="", META_API_KEY="")
        assert s.SPARK_REASONING_EFFORT_HIGH == "high"

    def test_reasoning_effort_method_low_calls(self) -> None:
        """_reasoning_effort returns low for verdict, verify_presence, extract_note."""
        from app.providers.meta import MetaAgentProvider
        with patch("app.providers.meta.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                MODEL_API_KEY="test", META_API_KEY="test",
                SPARK_REASONING_EFFORT="low", SPARK_REASONING_EFFORT_HIGH="high",
            )
            provider = MetaAgentProvider(client=MagicMock())
            assert provider._reasoning_effort("verdict") == "low"
            assert provider._reasoning_effort("verify_presence") == "low"
            assert provider._reasoning_effort("extract_note") == "low"

    def test_reasoning_effort_method_high_calls(self) -> None:
        """_reasoning_effort returns high for fix_plan and compile_template."""
        from app.providers.meta import MetaAgentProvider
        with patch("app.providers.meta.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                MODEL_API_KEY="test", META_API_KEY="test",
                SPARK_REASONING_EFFORT="low", SPARK_REASONING_EFFORT_HIGH="high",
            )
            provider = MetaAgentProvider(client=MagicMock())
            assert provider._reasoning_effort("fix_plan") == "high"
            assert provider._reasoning_effort("compile_template") == "high"

    def test_env_override_reasoning_effort(self) -> None:
        """SPARK_REASONING_EFFORT can be overridden via env."""
        with patch.dict(os.environ, {"SPARK_REASONING_EFFORT": "medium"}):
            s = Settings(MODEL_API_KEY="", META_API_KEY="")
            assert s.SPARK_REASONING_EFFORT == "medium"


# ── Item 3: smoke_meta.py structure ───────────────────────────────────────────


class TestSmokeMeta:
    """Test smoke_meta.py: no-key exit, concepts validation, independent steps."""

    def test_no_key_exits_nonzero(self) -> None:
        """smoke_meta.py exits 1 with 'NOT VERIFIED: no key' when MODEL_API_KEY is unset."""
        script = Path(__file__).resolve().parent.parent / "scripts" / "smoke_meta.py"
        env = {k: v for k, v in os.environ.items() if k not in ("MODEL_API_KEY", "META_API_KEY")}
        env["MODEL_API_KEY"] = ""
        env["META_API_KEY"] = ""
        result = subprocess.run(
            [sys.executable, str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"
        assert "NOT VERIFIED: no key" in result.stdout, f"Missing message in: {result.stdout}"

    def test_invalid_concept_exits_early(self) -> None:
        """smoke_meta.py rejects invalid concepts before any API call."""
        script = Path(__file__).resolve().parent.parent / "scripts" / "smoke_meta.py"
        env = dict(os.environ)
        env["MODEL_API_KEY"] = "fake-key-for-test"
        result = subprocess.run(
            [sys.executable, str(script), "--concepts", "not blocked exit"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1
        assert "Invalid concept" in result.stdout or "negation" in result.stdout.lower()

    def test_smoke_meta_has_concepts_flag(self) -> None:
        """smoke_meta.py --help mentions --concepts."""
        script = Path(__file__).resolve().parent.parent / "scripts" / "smoke_meta.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "--concepts" in result.stdout
        assert "--image" in result.stdout
        assert "--audio" in result.stdout
        assert "--record" in result.stdout


# ── Regression: existing schema tests still pass ──────────────────────────────


class TestVerdictSchemaRegression:
    """Ensure existing verdict validation still works after schema changes."""

    def test_valid_verdict(self) -> None:
        from app.providers.schemas import validate_verdict, VerdictStatus
        verdict = validate_verdict({
            "status": "pass",
            "reason": "Fire extinguisher present.",
            "cited_frame_ids": [0, 2],
            "confidence": 0.95,
        })
        assert verdict.status == VerdictStatus.PASS

    def test_backward_compat_aliases(self) -> None:
        from app.providers.schemas import validate_verdict, VerdictStatus
        verdict = validate_verdict({
            "verdict": "FAIL",
            "reason": "Exit path obstructed.",
            "cited_frames": ["4"],
            "confidence": 0.88,
        })
        assert verdict.status == VerdictStatus.FAIL
        assert verdict.cited_frame_ids == [4]

    def test_malformed_forces_unsure(self) -> None:
        from app.providers.schemas import validate_verdict, VerdictStatus
        verdict = validate_verdict("not json {")
        assert verdict.status == VerdictStatus.UNSURE
