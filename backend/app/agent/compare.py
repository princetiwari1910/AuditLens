"""Before-and-after audit comparison logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ComparisonStatus(str, Enum):
    RESOLVED = "resolved"           # fail -> pass
    NEW_ISSUE = "new_issue"         # pass -> fail
    STILL_OPEN = "still_open"       # fail -> fail
    UNCHANGED_PASS = "unchanged_pass" # pass -> pass
    UNSURE_CHANGE = "unsure_change" # any transition involving 'unsure'
    ADDED = "added"                 # rule only present in after audit
    REMOVED = "removed"             # rule only present in before audit


@dataclass
class RuleComparison:
    rule_id: str
    status: ComparisonStatus
    before_status: str | None
    after_status: str | None
    before_confidence: float | None
    after_confidence: float | None
    rule_title: str = ""
    rationale: str = ""
    fix_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "status": self.status.value,
            "before_status": self.before_status,
            "after_status": self.after_status,
            "before_confidence": self.before_confidence,
            "after_confidence": self.after_confidence,
            "rule_title": self.rule_title,
            "rationale": self.rationale,
            "fix_text": self.fix_text,
        }


def classify_transition(before_status: str | None, after_status: str | None) -> ComparisonStatus:
    """Classify the progression of a single rule between two audits."""
    if before_status is None and after_status is not None:
        return ComparisonStatus.ADDED
    if before_status is not None and after_status is None:
        return ComparisonStatus.REMOVED

    b = (before_status or "").lower()
    a = (after_status or "").lower()

    if b == "unsure" or a == "unsure":
        return ComparisonStatus.UNSURE_CHANGE
    if b == "fail" and a == "pass":
        return ComparisonStatus.RESOLVED
    if b == "pass" and a == "fail":
        return ComparisonStatus.NEW_ISSUE
    if b == "fail" and a == "fail":
        return ComparisonStatus.STILL_OPEN
    if b == "pass" and a == "pass":
        return ComparisonStatus.UNCHANGED_PASS

    return ComparisonStatus.UNSURE_CHANGE


def compare_audits(
    before_findings: list[dict[str, Any]],
    after_findings: list[dict[str, Any]],
    before_id: str = "",
    after_id: str = "",
) -> dict[str, Any]:
    """
    Compare findings from two audits matched by rule_id.
    Returns per-rule comparison results and aggregated summary counts.
    """
    before_by_rule = {f.get("rule_id", ""): f for f in before_findings if f.get("rule_id")}
    after_by_rule = {f.get("rule_id", ""): f for f in after_findings if f.get("rule_id")}

    all_rule_ids = list(dict.fromkeys(list(before_by_rule.keys()) + list(after_by_rule.keys())))

    comparisons: list[RuleComparison] = []
    counts = {
        "resolved": 0,
        "new_issue": 0,
        "still_open": 0,
        "unchanged_pass": 0,
        "unsure_change": 0,
        "added": 0,
        "removed": 0,
    }

    for r_id in all_rule_ids:
        b_find = before_by_rule.get(r_id)
        a_find = after_by_rule.get(r_id)

        b_stat = b_find.get("status") if b_find else None
        a_stat = a_find.get("status") if a_find else None

        trans = classify_transition(b_stat, a_stat)
        counts[trans.value] = counts.get(trans.value, 0) + 1

        b_conf = float(b_find["confidence"]) if b_find and "confidence" in b_find else None
        a_conf = float(a_find["confidence"]) if a_find and "confidence" in a_find else None

        title = (a_find or b_find or {}).get("rule_title", r_id)
        rationale = (a_find or b_find or {}).get("rationale", "")
        fix_text = (a_find or b_find or {}).get("fix_text", "")

        comparisons.append(
            RuleComparison(
                rule_id=r_id,
                status=trans,
                before_status=b_stat,
                after_status=a_stat,
                before_confidence=b_conf,
                after_confidence=a_conf,
                rule_title=title,
                rationale=rationale,
                fix_text=fix_text,
            )
        )

    return {
        "before_id": before_id,
        "after_id": after_id,
        "summary": counts,
        "results": [c.to_dict() for c in comparisons],
    }
