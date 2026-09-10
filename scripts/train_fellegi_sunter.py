#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fit and evaluate a Recordlane Fellegi-Sunter policy from labeled JSONL pairs."""

import argparse
import json
from pathlib import Path

from recordlane.matching import evaluate, fit_parameters
from recordlane.policy import compile_policy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=Path)
    parser.add_argument("labeled_pairs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.policy.read_text())
    pairs = [
        json.loads(line) for line in args.labeled_pairs.read_text().splitlines() if line
    ]
    compiled = compile_policy(document)
    candidate = compiled.canonical_document()
    candidate["matching"]["algorithm"] = "fellegi_sunter"
    candidate["matching"]["prior_match_probability"] = sum(
        int(row["is_match"]) for row in pairs
    ) / len(pairs)
    candidate["matching"]["comparisons"] = fit_parameters(
        pairs, candidate["matching"]["comparisons"]
    )
    trained = compile_policy(candidate)
    output = {
        "policy": trained.canonical_document(),
        "policy_checksum": trained.checksum,
        "evaluation": evaluate(trained, pairs),
        "method": "Fellegi-Sunter conditional-independence model with Laplace smoothing",
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
