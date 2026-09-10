# SPDX-License-Identifier: Apache-2.0
import re
import unicodedata
from typing import Any

from recordlane.policy import CompiledPolicy, compile_policy

SPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return SPACE.sub(" ", unicodedata.normalize("NFKC", value).strip()).casefold()


def normalize_record(
    values: dict[str, Any], policy: CompiledPolicy | dict[str, Any] | None = None
) -> dict[str, Any]:
    if policy is not None:
        runtime = policy if isinstance(policy, CompiledPolicy) else compile_policy(policy)
        return runtime.normalize(values)
    normalized: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, str):
            normalized[key] = normalize_text(value)
        elif isinstance(value, list):
            normalized[key] = [normalize_text(v) if isinstance(v, str) else v for v in value]
        else:
            normalized[key] = value
    return normalized


def validate_record(values: dict[str, Any], definition: dict[str, Any]) -> list[dict[str, str]]:
    return compile_policy(definition).validate(values)
