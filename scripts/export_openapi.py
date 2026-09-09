#!/usr/bin/env python3
"""Export the canonical API contract deterministically from the running code."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

from recordlane.main import app

root = Path(__file__).resolve().parents[1]
target = root / "contracts" / "openapi" / "openapi.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {target}")
