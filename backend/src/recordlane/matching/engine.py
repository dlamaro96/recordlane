# SPDX-License-Identifier: Apache-2.0
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any


@dataclass(frozen=True)
class MatchEvidence:
    score: float
    decision: str
    evidence: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    policy_version: str = "deterministic-1"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare(left: dict[str, Any], right: dict[str, Any]) -> MatchEvidence:
    evidence: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    for field in ("tax_id", "registration_number"):
        a, b = left.get(field), right.get(field)
        if a and b and a != b:
            contradictions.append({"field": field, "left": a, "right": b, "rule": "hard_identifier_conflict"})
    name_a, name_b = str(left.get("name", "")), str(right.get("name", ""))
    name_score = SequenceMatcher(None, name_a, name_b).ratio() if name_a and name_b else 0.0
    evidence.append({"field": "name", "comparator": "sequence_ratio", "score": round(name_score, 4), "weight": 0.65})
    email_equal = bool(left.get("email") and left.get("email") == right.get("email"))
    evidence.append({"field": "email", "comparator": "exact", "score": 1.0 if email_equal else 0.0, "weight": 0.2})
    country_equal = bool(left.get("country") and left.get("country") == right.get("country"))
    evidence.append({"field": "country", "comparator": "exact", "score": 1.0 if country_equal else 0.0, "weight": 0.15})
    score = round(name_score * 0.65 + email_equal * 0.2 + country_equal * 0.15, 4)
    if contradictions:
        decision = "keep_separate"
    elif score >= 0.84:
        decision = "auto_link"
    elif score >= 0.58:
        decision = "review"
    else:
        decision = "no_link"
    return MatchEvidence(score, decision, evidence, contradictions)

