# SPDX-License-Identifier: Apache-2.0
"""Reproducible Fellegi-Sunter parameter fitting and labeled-pair evaluation."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from recordlane.policy import CompiledPolicy


def _agreement(left: Any, right: Any, comparator: str) -> bool:
    if left in (None, "") or right in (None, ""):
        return False
    if comparator == "exact":
        return left == right
    if comparator == "sequence_ratio":
        return SequenceMatcher(None, str(left), str(right)).ratio() >= 0.85
    raise ValueError(f"unsupported comparator: {comparator}")


def fit_parameters(
    labeled_pairs: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    *,
    smoothing: float = 1.0,
) -> list[dict[str, Any]]:
    """Estimate m/u agreement probabilities from explicit match/non-match labels."""

    matches = [row for row in labeled_pairs if row["is_match"]]
    nonmatches = [row for row in labeled_pairs if not row["is_match"]]
    if not matches or not nonmatches:
        raise ValueError("training requires both matched and non-matched labeled pairs")
    output = []
    for comparison in comparisons:
        field = comparison["field"]
        comparator = comparison["comparator"]
        m_agree = sum(
            _agreement(row["left"].get(field), row["right"].get(field), comparator)
            for row in matches
        )
        u_agree = sum(
            _agreement(row["left"].get(field), row["right"].get(field), comparator)
            for row in nonmatches
        )
        m_probability = (m_agree + smoothing) / (len(matches) + 2 * smoothing)
        u_probability = (u_agree + smoothing) / (len(nonmatches) + 2 * smoothing)
        if m_probability <= u_probability:
            raise ValueError(f"field {field} does not discriminate matches from non-matches")
        output.append(
            comparison
            | {
                "m_probability": round(m_probability, 6),
                "u_probability": round(u_probability, 6),
            }
        )
    return output


def evaluate(policy: CompiledPolicy, labeled_pairs: list[dict[str, Any]]) -> dict[str, float | int]:
    true_positive = false_positive = true_negative = false_negative = 0
    brier = 0.0
    for row in labeled_pairs:
        result = policy.compare(policy.normalize(row["left"]), policy.normalize(row["right"]))
        predicted = result["score"] >= 0.5
        actual = bool(row["is_match"])
        true_positive += int(predicted and actual)
        false_positive += int(predicted and not actual)
        true_negative += int(not predicted and not actual)
        false_negative += int(not predicted and actual)
        brier += (result["score"] - int(actual)) ** 2
    precision = true_positive / (true_positive + false_positive or 1)
    recall = true_positive / (true_positive + false_negative or 1)
    return {
        "pairs": len(labeled_pairs),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "true_negative": true_negative,
        "false_negative": false_negative,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "brier_score": round(brier / (len(labeled_pairs) or 1), 6),
    }
