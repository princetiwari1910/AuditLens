"""Tests for WP16: Meta Stack Visibility and Escalation Cascade."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.config import Settings, get_settings
from app.providers.meta import MetaAgentProvider
from app.providers.mock import MockReasoner
from app.providers.schemas import VerdictStatus


def test_rejection_of_contributor_models_in_settings():
    """Settings validator rejects any model containing '-contributor'."""
    with pytest.raises(ValueError, match="'-contributor' models train on user content"):
        Settings(ESCALATION_MODEL="muse-wonder-1.0-contributor")

    with pytest.raises(ValueError, match="'-contributor' models train on user content"):
        Settings(MODEL_ID_AGENT="muse-spark-1.3-contributor")

    # Non-contributor is valid
    s = Settings(ESCALATION_MODEL="muse-wonder-1.0")
    assert s.ESCALATION_MODEL == "muse-wonder-1.0"


def test_meta_agent_provider_rejects_contributor_escalation_model():
    """MetaAgentProvider constructor rejects contributor escalation model."""
    mock_client = MagicMock()
    with pytest.raises(ValueError, match="rejected: '-contributor'"):
        MetaAgentProvider(
            client=mock_client,
            model_id="muse-spark-1.3",
            escalation_model="muse-wonder-1.0-contributor",
        )


def test_escalation_cascade_disabled_does_not_retry():
    """When ENABLE_ESCALATION_CASCADE=False, unsure verdict from Spark is returned as-is without retry."""
    mock_client = MagicMock()
    # Spark returns unsure verdict
    unsure_content = json.dumps({
        "verdict": "unsure",
        "reason": "Insufficient clarity to verify extinguisher",
        "cited_frame_ids": [0],
        "confidence": 0.50,
    })
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=unsure_content))]
    mock_client.chat.completions.create.return_value = mock_resp

    provider = MetaAgentProvider(
        client=mock_client,
        model_id="muse-spark-1.3",
        escalation_model="muse-wonder-1.0",
    )

    settings = get_settings()
    settings.ENABLE_ESCALATION_CASCADE = False

    rule = {"title": "Check Extinguisher", "description": "Fire extinguisher must be present"}
    evidence = [{"frame_id": 0, "label": "wall", "score": 0.4}]

    res = provider.judge(rule, evidence)
    assert res["status"] == "unsure"
    # Verify client.chat.completions.create called only once
    assert mock_client.chat.completions.create.call_count == 1
    assert mock_client.chat.completions.create.call_args[1]["model"] == "muse-spark-1.3"


def test_escalation_cascade_retries_once_when_unsure():
    """When ENABLE_ESCALATION_CASCADE=True and Spark returns unsure, retries once with escalation model."""
    mock_client = MagicMock()

    unsure_content = json.dumps({
        "verdict": "unsure",
        "reason": "Spark is unsure due to shadow",
        "cited_frame_ids": [0],
        "confidence": 0.45,
    })
    pass_content = json.dumps({
        "verdict": "pass",
        "reason": "Wonder model confirms extinguisher clearly visible",
        "cited_frame_ids": [0],
        "confidence": 0.92,
    })

    resp_unsure = MagicMock()
    resp_unsure.choices = [MagicMock(message=MagicMock(content=unsure_content))]

    resp_pass = MagicMock()
    resp_pass.choices = [MagicMock(message=MagicMock(content=pass_content))]

    # 1st call Spark returns unsure; 2nd call Wonder returns pass
    mock_client.chat.completions.create.side_effect = [resp_unsure, resp_pass]

    provider = MetaAgentProvider(
        client=mock_client,
        model_id="muse-spark-1.3",
        escalation_model="muse-wonder-1.0",
    )

    settings = get_settings()
    settings.ENABLE_ESCALATION_CASCADE = True

    rule = {"title": "Check Extinguisher", "description": "Fire extinguisher must be present"}
    evidence = [{"frame_id": 0, "label": "extinguisher", "score": 0.8}]

    res = provider.judge(rule, evidence)
    assert res["status"] == "pass"
    assert "[Escalated from muse-spark-1.3 to muse-wonder-1.0]" in res["reason"]
    assert mock_client.chat.completions.create.call_count == 2
    assert mock_client.chat.completions.create.call_args_list[0][1]["model"] == "muse-spark-1.3"
    assert mock_client.chat.completions.create.call_args_list[1][1]["model"] == "muse-wonder-1.0"


def test_escalation_cascade_falls_back_cleanly_on_failure():
    """If escalation model fails (e.g. timeout / error), falls back cleanly to original Spark verdict."""
    mock_client = MagicMock()

    unsure_content = json.dumps({
        "verdict": "unsure",
        "reason": "Spark cannot confirm due to occlusion",
        "cited_frame_ids": [0],
        "confidence": 0.40,
    })
    resp_unsure = MagicMock()
    resp_unsure.choices = [MagicMock(message=MagicMock(content=unsure_content))]

    # 1st call Spark succeeds; 2nd call Wonder raises runtime error
    mock_client.chat.completions.create.side_effect = [
        resp_unsure,
        RuntimeError("Wonder service temporarily overloaded"),
    ]

    provider = MetaAgentProvider(
        client=mock_client,
        model_id="muse-spark-1.3",
        escalation_model="muse-wonder-1.0",
    )

    settings = get_settings()
    settings.ENABLE_ESCALATION_CASCADE = True

    rule = {"title": "Check Extinguisher", "description": "Fire extinguisher must be present"}
    evidence = [{"frame_id": 0, "label": "extinguisher", "score": 0.8}]

    res = provider.judge(rule, evidence)
    # Should fall back cleanly to original Spark unsure verdict without crashing
    assert res["status"] == "unsure"
    assert "Spark cannot confirm due to occlusion" in res["reason"]


def test_mock_reasoner_rejects_contributor_escalation_model(monkeypatch: pytest.MonkeyPatch):
    """MockReasoner rejects -contributor escalation model when cascade is enabled."""
    monkeypatch.setattr(get_settings(), "ENABLE_ESCALATION_CASCADE", True)
    monkeypatch.setattr(get_settings(), "ESCALATION_MODEL", "muse-wonder-1.0-contributor")

    reasoner = MockReasoner()
    with pytest.raises(ValueError, match="'-contributor' models train on user content"):
        reasoner.verify_presence("fire extinguisher", [{"idx": 0, "path": "frame_0.jpg"}])
