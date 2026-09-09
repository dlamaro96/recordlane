#!/usr/bin/env python3
"""Validate a Recordlane configuration file without evaluating code."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import re
import sys
from pathlib import Path
import yaml

SECRET=re.compile(r"(^|_)(password|secret|token|private_key|client_secret)($|_)",re.I)

def walk(value, path="$"):
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET.search(str(key)): raise ValueError(f"secret-like key is forbidden at {path}.{key}; use a secret reference")
            walk(item,f"{path}.{key}")
    elif isinstance(value,list):
        for index,item in enumerate(value): walk(item,f"{path}[{index}]")

def main() -> None:
    if len(sys.argv)!=2: raise SystemExit("usage: validate_config.py path.yaml")
    path=Path(sys.argv[1]).resolve()
    if not path.is_file() or path.stat().st_size>2_000_000: raise SystemExit("configuration must be a file no larger than 2 MB")
    value=yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise SystemExit("configuration root must be a mapping")
    walk(value)
    if value.get("kind")=="DomainPack":
        if value.get("apiVersion")!="recordlane.io/v1alpha1": raise SystemExit("unsupported apiVersion")
        spec=value.get("spec",{}); metadata=value.get("metadata",{})
        for key in ("entity","mode","attributes","identifierNamespaces"):
            if key not in spec: raise SystemExit(f"domain pack spec.{key} is required")
        if spec["mode"] not in {"registry","consolidation","centralized","coexistence"}: raise SystemExit("unsupported mastering mode")
        if not re.fullmatch(r"[a-z][a-z0-9-]+",str(metadata.get("name",""))): raise SystemExit("invalid metadata.name")
    print(f"valid: {path} ({value.get('apiVersion','unversioned')} {value.get('kind','configuration')})")

if __name__=="__main__": main()
