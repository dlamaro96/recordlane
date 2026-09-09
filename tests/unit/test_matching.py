# SPDX-License-Identifier: Apache-2.0
from recordlane.matching import compare
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
    assert result.policy_version.startswith("policy:")
