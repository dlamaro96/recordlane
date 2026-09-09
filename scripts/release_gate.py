#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import yaml

data=yaml.safe_load(Path("REQUIREMENTS.yaml").read_text())
incomplete=[item for item in data["acceptance"] if item["status"] != "PASSED"]
if incomplete:
    for item in incomplete: print(f"{item['id']} {item['status']}: {item.get('blocker') or item['title']}")
    raise SystemExit(f"release blocked by {len(incomplete)} incomplete acceptance gates")
print("all mandatory acceptance gates passed")
