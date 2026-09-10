# SPDX-License-Identifier: Apache-2.0
from io import BytesIO, StringIO
import pytest

from recordlane.connectors.files import (
    iter_csv,
    iter_jsonl,
    iter_parquet,
    safe_csv_value,
    write_csv,
    write_jsonl,
    write_parquet,
)


def test_csv_stream_preserves_leading_zero_identifiers():
    rows = list(iter_csv(StringIO("id,name\n00042,Acme\n")))
    assert rows == [{"id": "00042", "name": "Acme"}]


def test_jsonl_rejects_non_object_and_reports_line():
    with pytest.raises(ValueError, match="line 2"):
        list(iter_jsonl(StringIO('{"id":"1"}\n[]\n')))


@pytest.mark.parametrize(
    "dangerous", ["=1+1", "+cmd", "-4+2", "@SUM(A:A)", "\tformula"]
)
def test_csv_export_neutralizes_formula_injection(dangerous):
    assert safe_csv_value(dangerous).startswith("'")


def test_all_file_formats_round_trip_multilingual_records():
    rows = [
        {"id": "1", "name": "Círculo"},
        {"id": "2", "name": "شركة النور"},
    ]
    csv_stream = StringIO()
    assert write_csv(iter(rows), csv_stream) == 2
    csv_stream.seek(0)
    assert list(iter_csv(csv_stream)) == rows

    jsonl_stream = StringIO()
    assert write_jsonl(iter(rows), jsonl_stream) == 2
    jsonl_stream.seek(0)
    assert list(iter_jsonl(jsonl_stream)) == rows

    parquet_stream = BytesIO()
    assert write_parquet(iter(rows), parquet_stream, batch_size=1) == 2
    parquet_stream.seek(0)
    assert list(iter_parquet(parquet_stream, batch_size=1)) == rows
