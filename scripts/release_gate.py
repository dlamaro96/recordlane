#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument(
    "--phase",
    choices=("prepublication", "final"),
    default="final",
    help="prepublication permits AX to be verified against a candidate release",
)
args = parser.parse_args()

acceptance_text = Path("REQUIREMENTS.yaml").read_text().split("\nacceptance:\n", 1)[1]
entries = [
    {"id": match.group(1), "status": match.group(2), "line": line.strip()}
    for line in acceptance_text.splitlines()
    if (match := re.match(r"\s*- \{id: ([A-Z]+), .* status: ([A-Z_]+),", line))
]
if len(entries) != 24:
    raise SystemExit(f"expected 24 acceptance entries, found {len(entries)}")
required = [
    item for item in entries if args.phase == "final" or item["id"] != "AX"
]
incomplete = [item for item in required if item["status"] != "PASSED"]
if incomplete:
    for item in incomplete:
        print(f"{item['id']} {item['status']}: {item['line']}")
    raise SystemExit(
        f"{args.phase} release blocked by {len(incomplete)} incomplete acceptance gates"
    )
print(f"all {args.phase} acceptance gates passed")
