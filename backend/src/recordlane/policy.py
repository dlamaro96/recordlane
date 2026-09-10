# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any


class PolicyError(ValueError):
    pass


NORMALIZERS = {"preserve", "uppercase_trim", "unicode_casefold"}
ATTRIBUTE_TYPES = {
    "string",
    "reference",
    "integer",
    "decimal",
    "boolean",
    "date",
    "datetime",
    "identifier",
    "enum",
}
SURVIVORSHIP_STRATEGIES = {
    "source_priority_then_observation_time",
    "verified_then_source_priority_then_observation_time",
}


def _text(value: str, mode: str) -> str:
    cleaned = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip())
    if mode == "preserve":
        return cleaned
    if mode == "uppercase_trim":
        return cleaned.upper()
    if mode == "unicode_casefold":
        return cleaned.casefold()
    raise PolicyError(f"unsupported normalizer: {mode}")


@dataclass(frozen=True)
class CompiledPolicy:
    document: dict[str, Any]
    version: str
    checksum: str

    @property
    def attributes(self) -> list[dict[str, Any]]:
        return self.document["attributes"]

    def normalize(self, values: dict[str, Any]) -> dict[str, Any]:
        attributes = {item["key"]: item for item in self.attributes}
        output: dict[str, Any] = {}
        for key, value in values.items():
            attribute = attributes.get(key)
            if value is None or not attribute:
                output[key] = value
                continue
            kind = attribute.get("type", "string")
            if kind == "decimal":
                try:
                    output[key] = str(Decimal(str(value)).normalize())
                except InvalidOperation:
                    output[key] = value
            elif isinstance(value, str):
                mode = attribute.get(
                    "normalizer",
                    "unicode_casefold" if kind in {"string", "reference"} else "preserve",
                )
                output[key] = _text(value, mode)
            elif isinstance(value, list):
                mode = attribute.get("normalizer", "unicode_casefold")
                output[key] = [
                    _text(item, mode) if isinstance(item, str) else item for item in value
                ]
            else:
                output[key] = value
        return output

    def validate(self, values: dict[str, Any]) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        for attribute in self.attributes:
            key = attribute["key"]
            value = values.get(key)
            name = attribute.get("name", key.replace("_", " "))
            if attribute.get("required") and (key not in values or value is None or value == ""):
                errors.append(
                    {"attribute": key, "code": "required", "message": f"{name} is required"}
                )
                continue
            allowed = attribute.get("allowed_values")
            if value is not None and allowed is not None and value not in allowed:
                errors.append(
                    {
                        "attribute": key,
                        "code": "allowed_values",
                        "message": f"{name} is not an allowed value",
                    }
                )
            pattern = attribute.get("pattern")
            if pattern and len(pattern) > 256:
                raise PolicyError(f"pattern for {key} exceeds 256 characters")
            if (
                value is not None
                and pattern
                and (not isinstance(value, str) or not re.fullmatch(pattern, value))
            ):
                errors.append(
                    {
                        "attribute": key,
                        "code": "pattern",
                        "message": f"{name} has an invalid format",
                    }
                )
            kind = attribute.get("type", "string")
            expected = {
                "string": str,
                "reference": str,
                "identifier": str,
                "enum": str,
                "integer": int,
                "boolean": bool,
            }.get(kind)
            if value is not None and expected and not isinstance(value, expected):
                errors.append(
                    {"attribute": key, "code": "type", "message": f"{name} must be {kind}"}
                )
        return errors

    def blocking_keys(self, normalized: dict[str, Any]) -> list[str]:
        output: list[str] = []
        for index, strategy in enumerate(self.document["matching"]["blocking"]):
            parts: list[str] = []
            for field in strategy.get("fields", []):
                value = normalized.get(field)
                if value in (None, ""):
                    parts = []
                    break
                parts.append(f"{field}={value}")
            prefix = strategy.get("prefix")
            if prefix:
                value = str(normalized.get(prefix["field"], ""))
                if not value:
                    parts = []
                else:
                    parts.append(f"{prefix['field']}^={value[: prefix['length']]}")
            if parts:
                output.append(f"p{index}|" + "|".join(parts))
        return output

    def compare(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        contradictions: list[dict[str, Any]] = []
        for identifier in self.document["identifiers"]:
            field = identifier["field"]
            a, b = left.get(field), right.get(field)
            if (
                a not in (None, "")
                and b not in (None, "")
                and a != b
                and identifier.get("hard_conflict", False)
            ):
                contradictions.append(
                    {
                        "field": field,
                        "namespace": identifier["namespace"],
                        "left": a,
                        "right": b,
                        "rule": "hard_identifier_conflict",
                    }
                )
        score = 0.0
        total_weight = 0.0
        log_likelihood = 0.0
        algorithm = self.document["matching"].get("algorithm", "weighted_score")
        for rule in self.document["matching"]["comparisons"]:
            field = rule["field"]
            a, b = left.get(field), right.get(field)
            comparator = rule["comparator"]
            if a in (None, "") or b in (None, ""):
                component = float(rule.get("missing_score", 0.0))
            elif comparator == "exact":
                component = 1.0 if a == b else 0.0
            elif comparator == "sequence_ratio":
                component = SequenceMatcher(None, str(a), str(b)).ratio()
            else:
                raise PolicyError(f"unsupported comparator: {comparator}")
            weight = float(rule["weight"])
            total_weight += weight
            score += component * weight
            item = {
                "field": field,
                "comparator": comparator,
                "score": round(component, 4),
                "weight": weight,
            }
            if algorithm == "fellegi_sunter":
                agreement = math.log(rule["m_probability"] / rule["u_probability"])
                disagreement = math.log((1 - rule["m_probability"]) / (1 - rule["u_probability"]))
                contribution = disagreement + component * (agreement - disagreement)
                log_likelihood += contribution
                item["log_likelihood_ratio"] = round(contribution, 4)
            evidence.append(item)
        if algorithm == "fellegi_sunter":
            prior = self.document["matching"]["prior_match_probability"]
            posterior_log_odds = math.log(prior / (1 - prior)) + log_likelihood
            score = round(1 / (1 + math.exp(-posterior_log_odds)), 6)
            score_kind = "estimated_match_probability"
        else:
            score = round(score / total_weight, 4) if total_weight else 0.0
            score_kind = "weighted_similarity"
        thresholds = self.document["matching"]["thresholds"]
        if contradictions:
            decision = "keep_separate"
        elif score >= thresholds["auto_link"]:
            decision = "auto_link"
        elif score >= thresholds["review"]:
            decision = "review"
        else:
            decision = "no_link"
        return {
            "score": score,
            "score_kind": score_kind,
            "decision": decision,
            "evidence": evidence,
            "contradictions": contradictions,
        }

    def canonical_document(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.document, sort_keys=True))


def compile_policy(definition: dict[str, Any]) -> CompiledPolicy:
    if definition.get("kind") == "DomainPack":
        if definition.get("apiVersion") != "recordlane.io/v1alpha1":
            raise PolicyError("unsupported domain-pack apiVersion")
        raw = dict(definition.get("spec", {}))
        version = str(definition.get("metadata", {}).get("version", "unversioned"))
    else:
        raw = dict(definition)
        version = str(
            definition.get("policy_version", definition.get("schema_version", "runtime-1"))
        )
    allowed_root = {
        "entity",
        "mode",
        "attributes",
        "identifiers",
        "identifierNamespaces",
        "matching",
        "survivorship",
        "relationships",
        "validation",
        "policy_version",
        "schema_version",
    }
    unknown = set(raw) - allowed_root
    if unknown:
        raise PolicyError(f"unsupported policy settings: {', '.join(sorted(unknown))}")
    attributes: list[dict[str, Any]] = []
    validation_by_field: dict[str, dict[str, Any]] = {}
    for rule in raw.get("validation", []):
        extra = set(rule) - {"attribute", "allowedValues"}
        if extra:
            raise PolicyError(
                f"unsupported validation settings for {rule.get('attribute', '?')}: "
                f"{', '.join(sorted(extra))}"
            )
        field = rule.get("attribute")
        if field:
            validation_by_field[field] = {
                "allowed_values": rule.get("allowedValues"),
            }
    for item in raw.get("attributes", []):
        allowed_attribute = {
            "key",
            "name",
            "type",
            "required",
            "allowed_values",
            "allowedValues",
            "pattern",
            "normalizer",
            "read_roles",
            "write_roles",
        }
        extra = set(item) - allowed_attribute
        if extra:
            settings = ", ".join(sorted(extra))
            raise PolicyError(
                f"unsupported attribute settings for {item.get('key', '?')}: {settings}"
            )
        attribute = dict(item)
        for access_key in ("read_roles", "write_roles"):
            if access_key in attribute:
                roles = attribute[access_key]
                if not isinstance(roles, list) or not all(
                    isinstance(role, str) and role for role in roles
                ):
                    raise PolicyError(f"{access_key} for {attribute.get('key', '?')} must be roles")
                attribute[access_key] = sorted(set(roles))
        if attribute.get("type", "string") not in ATTRIBUTE_TYPES:
            raise PolicyError(f"unsupported attribute type for {attribute.get('key', '?')}")
        if attribute.get("normalizer", "preserve") not in NORMALIZERS:
            raise PolicyError(f"unsupported normalizer for {attribute.get('key', '?')}")
        attribute["name"] = attribute.get("name", attribute["key"].replace("_", " ").capitalize())
        if "allowedValues" in attribute:
            attribute["allowed_values"] = attribute.pop("allowedValues")
        inherited = validation_by_field.get(attribute["key"], {})
        if inherited.get("allowed_values") is not None and "allowed_values" not in attribute:
            attribute["allowed_values"] = inherited["allowed_values"]
        attributes.append(attribute)
    identifiers = raw.get("identifiers")
    if identifiers is None:
        identifiers = [
            {"field": field, "namespace": field} for field in raw.get("identifierNamespaces", [])
        ]
    for item in identifiers:
        extra = set(item) - {"field", "key", "namespace", "hard_conflict"}
        if extra:
            raise PolicyError(
                f"unsupported identifier settings for {item.get('field', item.get('key', '?'))}: "
                f"{', '.join(sorted(extra))}"
            )
    identifiers = [
        {
            "field": item.get("field", item.get("key")),
            "namespace": item.get("namespace", item.get("field", item.get("key"))),
            "hard_conflict": bool(
                item.get(
                    "hard_conflict",
                    item.get("field", item.get("key"))
                    in raw.get("matching", {}).get("hard_conflicts", []),
                )
            ),
        }
        for item in identifiers
    ]
    matching = dict(raw.get("matching", {}))
    allowed_matching = {
        "blocking",
        "comparisons",
        "thresholds",
        "auto_link",
        "review",
        "hard_conflicts",
        "algorithm",
        "prior_match_probability",
    }
    extra_matching = set(matching) - allowed_matching
    if extra_matching:
        raise PolicyError(f"unsupported matching settings: {', '.join(sorted(extra_matching))}")
    blocking = matching.get("blocking", [])
    if blocking and all(isinstance(item, str) for item in blocking):
        fields = [item for item in blocking if item != "name_prefix"]
        strategy: dict[str, Any] = {"fields": fields}
        if "name_prefix" in blocking:
            strategy["prefix"] = {"field": "name", "length": 5}
        blocking = [strategy]
    for strategy in blocking:
        if not isinstance(strategy, dict) or set(strategy) - {"fields", "prefix"}:
            raise PolicyError("unsupported blocking strategy settings")
        prefix = strategy.get("prefix")
        if prefix:
            if set(prefix) != {"field", "length"}:
                raise PolicyError("blocking prefix requires only field and length")
            if not 1 <= int(prefix["length"]) <= 64:
                raise PolicyError("blocking prefix length must be between 1 and 64")
    comparisons = matching.get("comparisons", [])
    for rule in comparisons:
        if set(rule) - {
            "field",
            "comparator",
            "weight",
            "missing_score",
            "m_probability",
            "u_probability",
        }:
            raise PolicyError(f"unsupported comparison settings for {rule.get('field', '?')}")
        if rule.get("comparator") not in {"exact", "sequence_ratio"}:
            raise PolicyError(f"unsupported comparator: {rule.get('comparator')}")
        if float(rule.get("weight", 0)) <= 0:
            raise PolicyError("comparison weight must be positive")
    algorithm = matching.get("algorithm", "weighted_score")
    if algorithm not in {"weighted_score", "fellegi_sunter"}:
        raise PolicyError("unsupported matching algorithm")
    prior = float(matching.get("prior_match_probability", 0.01))
    if algorithm == "fellegi_sunter":
        if not 0 < prior < 1:
            raise PolicyError("Fellegi-Sunter prior_match_probability must be between zero and one")
        for rule in comparisons:
            m_probability = float(rule.get("m_probability", 0))
            u_probability = float(rule.get("u_probability", 0))
            if not 0 < u_probability < m_probability < 1:
                raise PolicyError(
                    "Fellegi-Sunter comparisons require 0 < u_probability < m_probability < 1"
                )
    thresholds = matching.get(
        "thresholds",
        {
            "auto_link": float(matching.get("auto_link", 1.01)),
            "review": float(matching.get("review", 1.01)),
        },
    )
    if not 0 <= float(thresholds["review"]) <= float(thresholds["auto_link"]) <= 1.01:
        raise PolicyError("matching thresholds must satisfy 0 <= review <= auto_link <= 1.01")
    survivorship = raw.get(
        "survivorship", {"default": "verified_then_source_priority_then_observation_time"}
    )
    attribute_keys = {item["key"] for item in attributes}
    if set(survivorship) - attribute_keys - {"default"}:
        raise PolicyError("survivorship contains an unknown attribute")
    for field, rule in survivorship.items():
        if isinstance(rule, str):
            strategy = rule
        elif isinstance(rule, dict) and not set(rule) - {"strategy", "source_precedence"}:
            strategy = rule.get("strategy")
        else:
            raise PolicyError(f"unsupported survivorship settings for {field}")
        if strategy not in SURVIVORSHIP_STRATEGIES:
            raise PolicyError(f"unsupported survivorship strategy for {field}: {strategy}")
    canonical = {
        "entity": raw.get("entity", "Entity"),
        "mode": raw.get("mode", "coexistence"),
        "attributes": attributes,
        "identifiers": identifiers,
        "relationships": raw.get("relationships", []),
        "matching": {
            "algorithm": algorithm,
            "prior_match_probability": prior,
            "blocking": blocking,
            "comparisons": comparisons,
            "thresholds": {
                "review": float(thresholds["review"]),
                "auto_link": float(thresholds["auto_link"]),
            },
        },
        "survivorship": survivorship,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return CompiledPolicy(canonical, version, hashlib.sha256(encoded).hexdigest())
