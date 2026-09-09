# SPDX-License-Identifier: Apache-2.0
from io import StringIO
import pytest

from recordlane.connectors.files import iter_csv, iter_jsonl, safe_csv_value


def test_csv_stream_preserves_leading_zero_identifiers():
    rows = list(iter_csv(StringIO("id,name\n00042,Acme\n")))
    assert rows == [{"id": "00042", "name": "Acme"}]


def test_jsonl_rejects_non_object_and_reports_line():
    with pytest.raises(ValueError, match="line 2"):
        list(iter_jsonl(StringIO('{"id":"1"}\n[]\n')))


@pytest.mark.parametrize("dangerous", ["=1+1", "+cmd", "-4+2", "@SUM(A:A)", "\tformula"])
def test_csv_export_neutralizes_formula_injection(dangerous):
    assert safe_csv_value(dangerous).startswith("'")

