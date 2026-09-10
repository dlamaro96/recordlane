# SPDX-License-Identifier: Apache-2.0
from dataclasses import asdict, dataclass
from typing import Any

from recordlane.policy import CompiledPolicy, compile_policy


@dataclass(frozen=True)
class MatchEvidence:
    score: float
    decision: str
    evidence: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    score_kind: str = "weighted_similarity"
    policy_version: str = "deterministic-1"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare(
    left: dict[str, Any],
    right: dict[str, Any],
    policy: CompiledPolicy | dict[str, Any] | None = None,
) -> MatchEvidence:
    runtime = policy if isinstance(policy, CompiledPolicy) else compile_policy(policy or {})
    result = runtime.compare(left, right)
    return MatchEvidence(
        result["score"],
        result["decision"],
        result["evidence"],
        result["contradictions"],
        result["score_kind"],
        f"policy:{runtime.version}:{runtime.checksum[:12]}",
    )
