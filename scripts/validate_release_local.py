#!/usr/bin/env python3
"""Run reproducible local validation and persist sanitized command evidence."""

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import json
import os
import platform
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
python_sdk = root.parent / "recordlane-python"
ecosystem = root.parent / "recordlane-ecosystem"


def repository_pytest(repository: Path, variable: str) -> list[str]:
    configured = os.environ.get(variable)
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [repository / ".venv/bin/python", repository / ".venv/Scripts/python.exe"]
    )
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate), "-m", "pytest"]
    raise SystemExit(
        f"No pytest for {repository.name}; create {repository / '.venv'} or set {variable}"
    )


steps = [
    (
        "requirements",
        [
            str(root / "backend/.venv/bin/python"),
            str(root / "scripts/validate_requirements.py"),
        ],
        root,
        None,
    ),
    (
        "platform tests",
        [
            str(root / "backend/.venv/bin/pytest"),
            "tests/unit",
            "tests/property",
            "tests/integration",
        ],
        root,
        {
            "RECORDLANE_DEMO_MODE": "true",
            "RECORDLANE_DATABASE_URL": f"sqlite:///{tempfile.mkdtemp(prefix='recordlane-validation-')}/test.db",
        },
    ),
    ("web unit", ["npm", "test"], root / "apps/web", None),
    ("web build", ["npm", "run", "build"], root / "apps/web", None),
    ("web e2e", ["npm", "run", "test:e2e"], root / "apps/web", None),
    (
        "compose config",
        [
            "docker",
            "compose",
            "-f",
            "deploy/compose/compose.demo.yaml",
            "config",
            "--quiet",
        ],
        root,
        None,
    ),
    ("helm lint", ["helm", "lint", "deploy/helm/recordlane"], root, None),
    (
        "helm render",
        [
            "helm",
            "template",
            "recordlane",
            "deploy/helm/recordlane",
            "--set",
            "oidc.issuer=https://id.example/realms/recordlane",
            "--set",
            "oidc.audience=recordlane-api",
        ],
        root,
        None,
    ),
    (
        "python sdk live",
        [*repository_pytest(python_sdk, "RECORDLANE_PYTHON_SDK_PYTHON"), "tests"],
        python_sdk,
        {"PYTHONPATH": str(python_sdk / "src")},
    ),
    (
        "typescript sdk unit",
        ["npm", "test"],
        root.parent / "recordlane-typescript",
        None,
    ),
    (
        "typescript sdk build",
        ["npm", "run", "build"],
        root.parent / "recordlane-typescript",
        None,
    ),
    (
        "typescript sdk live",
        ["npm", "run", "test:live"],
        root.parent / "recordlane-typescript",
        None,
    ),
    (
        "connector conformance",
        [*repository_pytest(ecosystem, "RECORDLANE_ECOSYSTEM_PYTHON"), "tests"],
        ecosystem,
        {"PYTHONPATH": str(ecosystem / "src")},
    ),
    ("docs check", ["npm", "test"], root.parent / "recordlane-docs", None),
    ("docs build", ["npm", "run", "build"], root.parent / "recordlane-docs", None),
]
evidence = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "host": platform.platform(),
    "machine": platform.machine(),
    "steps": [],
}
for name, command, cwd, extra_env in steps:
    env = os.environ.copy()
    env.update(extra_env or {})
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    evidence["steps"].append(
        {
            "name": name,
            "command": command,
            "cwd": str(cwd),
            "exit_code": result.returncode,
            "output": result.stdout[-12000:],
        }
    )
    print(f"{'PASS' if result.returncode == 0 else 'FAIL'} {name}")
target = root / "docs/evidence/2026-09-09/validation.json"
target.write_text(json.dumps(evidence, indent=2) + "\n")
if any(step["exit_code"] for step in evidence["steps"]):
    raise SystemExit("one or more validation steps failed; see evidence file")
