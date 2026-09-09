#!/usr/bin/env python3
"""Reproducible synthetic matcher throughput and ground-truth report."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import json
import platform
import random
import time
from pathlib import Path
from recordlane.matching.engine import compare
from recordlane.quality.engine import normalize_record

rng=random.Random(741_902)
first=["Acme","Harbor","Meridian","Northstar","Cedar","Atlas","Nile","Sierra","Delta","Lumen"]
last=["Industrial","Logistics","Foods","Works","Trading","Medical","Components","Services"]
countries=["US","AE","ES","DE"]
pairs=[]
for index in range(10_000):
    name=f"{rng.choice(first)} {rng.choice(last)} {index}"
    country=rng.choice(countries); tax=f"{country}-{index:07d}"
    left=normalize_record({"name":name,"country":country,"tax_id":tax,"email":f"ops{index}@example.invalid"})
    if index%2==0:
        right=normalize_record({**left,"name":name.replace("Industrial","Indstrial")}); truth=True
    else:
        other=index+1_000_000; right=normalize_record({"name":f"{rng.choice(first)} {rng.choice(last)} {other}","country":country,"tax_id":f"{country}-{other:07d}","email":f"ops{other}@example.invalid"}); truth=False
    pairs.append((left,right,truth))
start=time.perf_counter(); results=[compare(a,b) for a,b,_ in pairs]; elapsed=time.perf_counter()-start
tp=tn=fp=fn=0
for result,(_,_,truth) in zip(results,pairs,strict=True):
    predicted=result.decision in {"auto_link","review"}
    tp+=truth and predicted; tn+=(not truth) and (not predicted); fp+=(not truth) and predicted; fn+=truth and (not predicted)
report={"generated_at":"2026-09-09","workload":"10,000 deterministic normalized synthetic labeled pairs; 50% near-duplicate, 50% hard-identifier-distinct","seed":741902,"hardware":platform.platform(),"python":platform.python_version(),"elapsed_seconds":round(elapsed,6),"pairs_per_second":round(len(pairs)/elapsed,2),"confusion_matrix":{"true_positive":tp,"true_negative":tn,"false_positive":fp,"false_negative":fn},"accuracy":round((tp+tn)/len(pairs),6),"limitations":["single-process in-memory comparison only","synthetic names are not representative production data","no database candidate-generation or concurrency included","not a competitor comparison or capacity guarantee"]}
target=Path(__file__).parents[1]/"docs/evidence/2026-09-09/matching-benchmark.json"; target.write_text(json.dumps(report,indent=2)+"\n"); print(json.dumps(report,indent=2))
