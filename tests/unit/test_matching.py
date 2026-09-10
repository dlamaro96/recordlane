# SPDX-License-Identifier: Apache-2.0
from recordlane.matching import compare, evaluate, fit_parameters
from recordlane.demo import SUPPLIER_DEFINITION
from recordlane.policy import compile_policy


POLICY = compile_policy(SUPPLIER_DEFINITION)


def test_hard_identifier_contradiction_overrides_high_similarity():
    result = compare(
        {"name": "northstar components llc", "tax_id": "US00184", "country": "US"},
        {"name": "northstar components llc", "tax_id": "US99999", "country": "US"},
        POLICY,
    )
    assert result.decision == "keep_separate"
    assert result.contradictions[0]["rule"] == "hard_identifier_conflict"


def test_score_is_disclosed_as_weighted_score_not_probability():
    result = compare(
        {"name": "harbor metals llc", "email": "buy@harbor.example", "country": "US"},
        {"name": "harbor metal", "email": "buy@harbor.example", "country": "US"},
        POLICY,
    )
    assert result.score >= 0.58
    assert result.score_kind == "weighted_similarity"
    assert result.policy_version.startswith("policy:")


def test_fellegi_sunter_uses_likelihood_parameters_and_reports_probability():
    definition = POLICY.canonical_document()
    definition["matching"] = definition["matching"] | {
        "algorithm": "fellegi_sunter",
        "prior_match_probability": 0.02,
        "comparisons": [
            {
                "field": "name",
                "comparator": "exact",
                "weight": 1,
                "m_probability": 0.95,
                "u_probability": 0.01,
            },
            {
                "field": "country",
                "comparator": "exact",
                "weight": 1,
                "m_probability": 0.98,
                "u_probability": 0.2,
            },
        ],
        "thresholds": {"review": 0.5, "auto_link": 0.9},
    }
    probabilistic = compile_policy(definition)
    match = compare(
        {"name": "northstar", "country": "US"},
        {"name": "northstar", "country": "US"},
        probabilistic,
    )
    nonmatch = compare(
        {"name": "northstar", "country": "US"},
        {"name": "southstar", "country": "DE"},
        probabilistic,
    )
    assert match.score_kind == "estimated_match_probability"
    assert match.score > 0.9
    assert nonmatch.score < 0.01
    assert "log_likelihood_ratio" in match.evidence[0]


def test_fellegi_sunter_training_and_evaluation_are_reproducible():
    pairs = [
        {
            "left": {"name": "north", "country": "US"},
            "right": {"name": "north", "country": "US"},
            "is_match": True,
        },
        {
            "left": {"name": "harbor", "country": "AE"},
            "right": {"name": "harbor", "country": "AE"},
            "is_match": True,
        },
        {
            "left": {"name": "north", "country": "US"},
            "right": {"name": "south", "country": "DE"},
            "is_match": False,
        },
        {
            "left": {"name": "harbor", "country": "AE"},
            "right": {"name": "mesa", "country": "ES"},
            "is_match": False,
        },
    ]
    comparisons = [
        {"field": "name", "comparator": "exact", "weight": 1},
        {"field": "country", "comparator": "exact", "weight": 1},
    ]
    fitted = fit_parameters(pairs, comparisons)
    definition = POLICY.canonical_document()
    definition["matching"] = definition["matching"] | {
        "algorithm": "fellegi_sunter",
        "prior_match_probability": 0.5,
        "comparisons": fitted,
        "thresholds": {"review": 0.5, "auto_link": 0.9},
    }
    metrics = evaluate(compile_policy(definition), pairs)
    assert metrics["precision"] == 1
    assert metrics["recall"] == 1
    assert metrics["brier_score"] < 0.1
