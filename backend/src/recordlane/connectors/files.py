# SPDX-License-Identifier: Apache-2.0
import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO


MAX_CELL_CHARS = 1_000_000


def _bounded(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
        raise ValueError("cell exceeds configured size limit")
    return value


def iter_csv(stream: TextIO) -> Iterator[dict[str, str]]:
    for row in csv.DictReader(stream):
        yield {key: _bounded(value) for key, value in row.items()}


def iter_jsonl(stream: TextIO) -> Iterator[dict[str, Any]]:
    for line_number, line in enumerate(stream, 1):
        if len(line) > MAX_CELL_CHARS * 4:
            raise ValueError(f"line {line_number} exceeds configured size limit")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"line {line_number} must contain an object")
        yield value


def safe_csv_value(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text

