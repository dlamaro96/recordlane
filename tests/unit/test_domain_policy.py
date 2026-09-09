# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest
import yaml

from recordlane.policy import PolicyError, compile_policy


ROOT = Path(__file__).resolve().parents[2]


def test_every_bundled_domain_pack_compiles_and_round_trips():
    paths = sorted((ROOT / "domains").glob("*/v1alpha1.yaml"))
    assert len(paths) == 6
    for path in paths:
        runtime = compile_policy(yaml.safe_load(path.read_text()))
        round_tripped = compile_policy(runtime.canonical_document())
        assert round_tripped.canonical_document() == runtime.canonical_document()


def test_supplier_and_product_matching_differ_without_python_changes():
    supplier = compile_policy(
        yaml.safe_load((ROOT / "domains/supplier/v1alpha1.yaml").read_text())
    )
    product = compile_policy(
        yaml.safe_load((ROOT / "domains/product/v1alpha1.yaml").read_text())
    )
    left = {
        "name": "Atlas valve",
        "tax_id": "US001",
        "country": "US",
        "sku": "00042",
        "category": "valves",
    }
    right = {
        "name": "Atlas valve",
        "tax_id": "US999",
        "country": "US",
        "sku": "00042",
        "category": "valves",
    }
    assert supplier.compare(left, right)["decision"] == "keep_separate"
    assert product.compare(left, right)["decision"] == "auto_link"


def test_unknown_behavioral_setting_is_rejected():
    with pytest.raises(PolicyError, match="unsupported matching settings"):
        compile_policy(
            {
                "attributes": [{"key": "name", "type": "string"}],
                "matching": {"magic_ai_confidence": True},
            }
        )


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (
            {
                "attributes": [{"key": "name", "type": "string"}],
                "identifiers": [{"field": "name", "unique": True}],
            },
            "unsupported identifier settings",
        ),
        (
            {
                "attributes": [{"key": "name", "type": "string"}],
                "validation": [{"attribute": "name", "uniqueWithin": "tenant"}],
            },
            "unsupported validation settings",
        ),
        (
            {
                "attributes": [{"key": "name", "type": "string"}],
                "survivorship": {"name": "newest_nonempty_magic"},
            },
            "unsupported survivorship strategy",
        ),
    ],
)
def test_unsupported_nested_behavior_is_never_silently_ignored(document, message):
    with pytest.raises(PolicyError, match=message):
        compile_policy(document)
