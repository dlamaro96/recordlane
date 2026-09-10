#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproducible synthetic matcher scale and ground-truth report."""

from __future__ import annotations

import argparse
import json
import platform
import random
import resource
import time
from pathlib import Path

from recordlane.matching.engine import compare
from recordlane.policy import compile_policy
from recordlane.quality.engine import normalize_record

SEED = 741_902
FIRST = [
    "Acme",
    "Harbor",
    "Meridian",
    "Northstar",
    "Cedar",
    "Atlas",
    "Nile",
    "Sierra",
    "Delta",
    "Lumen",
]
LAST = [
    "Industrial",
    "Logistics",
    "Foods",
    "Works",
    "Trading",
    "Medical",
    "Components",
    "Services",
]
COUNTRIES = ["US", "AE", "ES", "DE"]
POLICY = compile_policy(
    {
        "entity": "benchmark_supplier",
        "attributes": [
            {"key": "name", "type": "string", "normalizer": "unicode_casefold"},
            {"key": "country", "type": "string", "normalizer": "uppercase_trim"},
            {"key": "tax_id", "type": "identifier", "normalizer": "uppercase_trim"},
            {"key": "email", "type": "string", "normalizer": "unicode_casefold"},
        ],
        "identifiers": [
            {"field": "tax_id", "namespace": "tax", "hard_conflict": True}
        ],
        "matching": {
            "comparisons": [
                {"field": "tax_id", "comparator": "exact", "weight": 0.55},
                {"field": "name", "comparator": "sequence_ratio", "weight": 0.30},
                {"field": "email", "comparator": "exact", "weight": 0.15},
            ],
            "thresholds": {"review": 0.7, "auto_link": 0.88},
        },
    }
)


def generate(pair_count: int) -> list[tuple[dict, dict, bool]]:
    rng = random.Random(SEED)
    pairs = []
    for index in range(pair_count):
        # Repeated prefixes deliberately create skew; the unique suffix and hard ID
        # make this an invariant/throughput exercise, not a production-accuracy claim.
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)} {index % 250} {index}"
        country = rng.choice(COUNTRIES)
        tax = f"{country}-{index:07d}"
        left = normalize_record(
            {
                "name": name,
                "country": country,
                "tax_id": tax,
                "email": f"ops{index}@example.invalid",
            }
        )
        if index % 2 == 0:
            right = normalize_record(
                {**left, "name": name.replace("Industrial", "Indstrial")}
            )
            truth = True
        else:
            other = index + 1_000_000
            right = normalize_record(
                {
                    "name": f"{rng.choice(FIRST)} {rng.choice(LAST)} {index % 250} {other}",
                    "country": country,
                    "tax_id": f"{country}-{other:07d}",
                    "email": f"ops{other}@example.invalid",
                }
            )
            truth = False
        pairs.append((left, right, truth))
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-records", type=int, default=100_000)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parents[1]
        / "docs/evidence/2026-09-09/matching-benchmark.json",
    )
    args = parser.parse_args()
    if args.source_records < 2 or args.source_records % 2:
        raise SystemExit("--source-records must be an even integer of at least 2")

    pairs = generate(args.source_records // 2)
    started = time.perf_counter()
    results = [compare(left, right, POLICY) for left, right, _truth in pairs]
    elapsed = time.perf_counter() - started
    tp = tn = fp = fn = 0
    for result, (_left, _right, truth) in zip(results, pairs, strict=True):
        predicted = result.decision in {"auto_link", "review"}
        tp += bool(truth and predicted)
        tn += bool(not truth and not predicted)
        fp += bool(not truth and predicted)
        fn += bool(truth and not predicted)
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = max_rss if platform.system() == "Darwin" else max_rss * 1024
    report = {
        "generated_at": "2026-09-10",
        "workload": (
            f"{args.source_records:,} normalized synthetic source records in "
            f"{len(pairs):,} labeled comparisons; 50% near-duplicate, "
            "50% hard-identifier-distinct; skewed common-name prefixes"
        ),
        "seed": SEED,
        "hardware": platform.platform(),
        "python": platform.python_version(),
        "elapsed_seconds": round(elapsed, 6),
        "source_records_per_second": round(args.source_records / elapsed, 2),
        "comparisons_per_second": round(len(pairs) / elapsed, 2),
        "process_peak_rss_bytes": rss_bytes,
        "confusion_matrix": {
            "true_positive": tp,
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
        },
        "pairwise_accuracy": round((tp + tn) / len(pairs), 6),
        "targets_file": "matching-benchmark-targets.json",
        "limitations": [
            "single-process in-memory normalization/comparison only",
            "synthetic labels are not representative production data",
            "database candidate generation, API latency, and concurrency are excluded",
            "not a competitor comparison, capacity guarantee, or real-world precision claim",
        ],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
