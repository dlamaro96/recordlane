# SPDX-License-Identifier: Apache-2.0
import csv
import json
from collections.abc import Iterator
from itertools import chain
from typing import Any, BinaryIO, TextIO

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


def write_csv(rows: Iterator[dict[str, Any]], stream: TextIO) -> int:
    iterator = iter(rows)
    try:
        first = next(iterator)
    except StopIteration:
        return 0
    fields = list(first)
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
    writer.writeheader()
    count = 0
    for row in chain((first,), iterator):
        writer.writerow({key: safe_csv_value(row.get(key)) for key in fields})
        count += 1
    return count


def write_jsonl(rows: Iterator[dict[str, Any]], stream: TextIO) -> int:
    count = 0
    for row in rows:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        count += 1
    return count


def iter_parquet(stream: BinaryIO, batch_size: int = 1_000) -> Iterator[dict[str, Any]]:
    import pyarrow.parquet as parquet

    source = parquet.ParquetFile(stream)
    for batch in source.iter_batches(batch_size=batch_size):
        yield from batch.to_pylist()


def write_parquet(rows: Iterator[dict[str, Any]], stream: BinaryIO, batch_size: int = 1_000) -> int:
    import pyarrow as arrow
    import pyarrow.parquet as parquet

    writer = None
    buffered: list[dict[str, Any]] = []
    count = 0
    try:
        for row in rows:
            buffered.append(row)
            if len(buffered) < batch_size:
                continue
            table = arrow.Table.from_pylist(buffered)
            writer = writer or parquet.ParquetWriter(stream, table.schema)
            writer.write_table(table)
            count += len(buffered)
            buffered.clear()
        if buffered:
            table = arrow.Table.from_pylist(buffered)
            writer = writer or parquet.ParquetWriter(stream, table.schema)
            writer.write_table(table)
            count += len(buffered)
        return count
    finally:
        if writer:
            writer.close()
