#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate Recordlane configuration without evaluating user-controlled code."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from recordlane.policy import PolicyError, compile_policy  # noqa: E402

SECRET = re.compile(
    r"(^|_)(password|secret|token|private_key|client_secret)($|_)", re.IGNORECASE
)


def walk(value, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            is_reference = key_text.endswith("_ref") or key_text == "secret_references"
            if SECRET.search(key_text) and not is_reference:
                raise ValueError(
                    f"secret-like key is forbidden at {path}.{key}; use a secret reference"
                )
            walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            walk(item, f"{path}[{index}]")


def validate_domain_pack(value: dict) -> None:
    if value.get("apiVersion") != "recordlane.io/v1alpha1":
        raise SystemExit("unsupported apiVersion")
    spec = value.get("spec", {})
    metadata = value.get("metadata", {})
    for key in ("entity", "mode", "attributes", "identifierNamespaces"):
        if key not in spec:
            raise SystemExit(f"domain pack spec.{key} is required")
    if spec["mode"] not in {
        "registry",
        "consolidation",
        "centralized",
        "coexistence",
    }:
        raise SystemExit("unsupported mastering mode")
    if not re.fullmatch(r"[a-z][a-z0-9-]+", str(metadata.get("name", ""))):
        raise SystemExit("invalid metadata.name")
    try:
        compile_policy(value)
    except PolicyError as exc:
        raise SystemExit(str(exc)) from exc


def validate_workspace_bundle(value: dict) -> None:
    if value.get("apiVersion") != "recordlane.io/v1alpha1":
        raise SystemExit("unsupported apiVersion")
    spec = value.get("spec")
    if not isinstance(spec, dict):
        raise SystemExit("workspace bundle spec is required")
    domains = spec.get("domains")
    sources = spec.get("sources")
    configurations = spec.get("configurations")
    if not isinstance(domains, list) or not domains:
        raise SystemExit("workspace bundle must contain domains")
    if not isinstance(sources, list) or not isinstance(configurations, list):
        raise SystemExit("workspace bundle sources/configurations must be lists")
    for index, domain in enumerate(domains):
        if not isinstance(domain, dict) or not domain.get("key") or not domain.get("name"):
            raise SystemExit(f"workspace bundle domain {index} is invalid")
        try:
            compile_policy(domain.get("definition", {}))
        except PolicyError as exc:
            raise SystemExit(f"workspace bundle domain {index}: {exc}") from exc
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or not source.get("key") or not source.get("kind"):
            raise SystemExit(f"workspace bundle source {index} is invalid")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_config.py path.yaml")
    path = Path(sys.argv[1]).resolve()
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise SystemExit("configuration must be a file no larger than 2 MB")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("configuration root must be a mapping")
    try:
        walk(value)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if value.get("kind") == "DomainPack":
        validate_domain_pack(value)
    elif value.get("kind") == "WorkspaceBundle":
        validate_workspace_bundle(value)
    print(
        f"valid: {path} "
        f"({value.get('apiVersion', 'unversioned')} {value.get('kind', 'configuration')})"
    )


if __name__ == "__main__":
    main()
