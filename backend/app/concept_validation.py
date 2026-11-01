"""Validation for SAM 3.1 concept prompts to enforce plain noun phrases."""

from __future__ import annotations

import re

# Regex patterns for forbidden prompt elements
FORBIDDEN_CONJUNCTION_PATTERN = re.compile(r"\b(and|or)\b", re.IGNORECASE)

FORBIDDEN_NEGATION_PATTERNS = [
    re.compile(r"\b(not|no|neither|nor|unblocked)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+blocked\b", re.IGNORECASE),
    re.compile(r"\bnot\s+obstructed\b", re.IGNORECASE),
]

FORBIDDEN_SPATIAL_PATTERNS = [
    re.compile(r"\bon\s+(the\s+)?(left|right|top|bottom|floor|ground|wall)\b", re.IGNORECASE),
    re.compile(r"\bon\s+floor\b", re.IGNORECASE),
    re.compile(r"\bto\s+the\s+(left|right)\b", re.IGNORECASE),
    re.compile(r"\bin\s+the\s+(middle|center|background|foreground)\b", re.IGNORECASE),
    re.compile(r"\b(near|next\s+to|behind|in\s+front\s+of|beside|under|above|below)\b", re.IGNORECASE),
    re.compile(r"\b(blocking|obstructing|blocked|obstructed|clear\s+of\s+obstacles)\b", re.IGNORECASE),
    re.compile(r"\b(left|right|middle|center|background|foreground)\b", re.IGNORECASE),
]


def validate_concept(prompt: str, rule_id: str | None = None) -> str:
    """
    Validate that a concept prompt is a single plain noun phrase.

    Rejects:
    - Commas (multiple concepts)
    - Conjunctions ("and" / "or")
    - Negation ("not", "no", "unblocked", etc.)
    - Spatial words ("on the left", "in the middle", "blocking", "near", etc.)

    Raises ValueError with a clear error naming the rule and the concept if invalid.
    Returns the cleaned prompt (stripped) if valid, without rewriting its words.
    """
    rule_prefix = f"Rule '{rule_id}': " if rule_id else ""

    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"{rule_prefix}concept prompt must be a non-empty string.")

    cleaned = prompt.strip()

    if "," in cleaned:
        raise ValueError(
            f"{rule_prefix}concept '{cleaned}' contains commas. "
            "SAM 3.1 requires a single plain noun phrase per prompt (no comma-separated lists)."
        )

    if FORBIDDEN_CONJUNCTION_PATTERN.search(cleaned):
        raise ValueError(
            f"{rule_prefix}concept '{cleaned}' contains conjunction ('and'/'or'). "
            "Templates must use plain noun phrases only."
        )

    for pattern in FORBIDDEN_NEGATION_PATTERNS:
        if pattern.search(cleaned):
            raise ValueError(
                f"{rule_prefix}concept '{cleaned}' contains negation. "
                "Templates must use plain noun phrases only. Negation logic belongs in the rule engine."
            )

    for pattern in FORBIDDEN_SPATIAL_PATTERNS:
        if pattern.search(cleaned):
            raise ValueError(
                f"{rule_prefix}concept '{cleaned}' contains spatial words. "
                "Templates must use plain noun phrases only. Spatial and clearance logic belong in the rule engine."
            )

    return cleaned
