#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import yaml

root = Path(__file__).resolve().parents[1]
requirements = yaml.safe_load((root / "REQUIREMENTS.yaml").read_text())
errors = []
ids = [item["id"] for item in requirements["requirements"]]
if ids != [f"R{i:02d}" for i in range(1, 31)]:
    errors.append("requirement IDs must cover R01-R30 in order")
acceptance = [item["id"] for item in requirements["acceptance"]]
if acceptance != [f"A{chr(65+i)}" for i in range(24)]:
    errors.append("acceptance IDs must cover AA-AX in order")
for filename in ["SPEC.md", "AGENTS.md", "IMPLEMENTATION_PLAN.md", "DECISIONS.md", "STATUS.md", "RELEASE_READINESS.md"]:
    if not (root / filename).is_file():
        errors.append(f"missing {filename}")
if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f"validated {len(ids)} requirements and {len(acceptance)} acceptance scenarios")

