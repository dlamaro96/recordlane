# SPDX-License-Identifier: Apache-2.0
import re
import unicodedata
from typing import Any


SPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return SPACE.sub(" ", unicodedata.normalize("NFKC", value).strip()).casefold()


def normalize_record(values: dict[str, Any]) -> dict[str, Any]:
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
    errors: list[dict[str, str]] = []
    for attr in definition.get("attributes", []):
        key = attr["key"]
        value = values.get(key)
        if attr.get("required") and (key not in values or value is None or value == ""):
            errors.append({"attribute": key, "code": "required", "message": f"{attr['name']} is required"})
        if value is not None and "allowed_values" in attr and value not in attr["allowed_values"]:
            errors.append({"attribute": key, "code": "allowed_values", "message": f"{attr['name']} is not an allowed value"})
        pattern = attr.get("pattern")
        if value is not None and pattern and (not isinstance(value, str) or not re.fullmatch(pattern, value)):
            errors.append({"attribute": key, "code": "pattern", "message": f"{attr['name']} has an invalid format"})
    return errors

