# SPDX-License-Identifier: Apache-2.0
from hypothesis import given, strategies as st

from recordlane.quality.engine import normalize_text


@given(st.text(max_size=200))
def test_normalization_is_idempotent(value: str):
    assert normalize_text(normalize_text(value)) == normalize_text(value)


def test_arabic_and_diacritics_are_preserved():
    assert "الميناء" in normalize_text(" شركة الميناء ")
    assert normalize_text("Málaga") == "málaga"

