from __future__ import annotations

import pytest

from clip.validation import chunk_name, page, session_id


def test_session_ids_are_strict() -> None:
    assert session_id("20260716022113") == "20260716022113"
    for invalid in ("", "2026071602211", "20260716022113/", "abcdefghijklmn"):
        with pytest.raises(ValueError):
            session_id(invalid)


def test_chunk_names_cannot_be_paths() -> None:
    assert chunk_name("0001.opus") == "0001.opus"
    for invalid in ("0000.opus", "00001.opus", "../0001.opus", "0001.wav", "1.opus"):
        with pytest.raises(ValueError):
            chunk_name(invalid)


def test_page_values_are_bounded() -> None:
    assert page(1, maximum=50) == 1
    with pytest.raises(ValueError):
        page(0)
    with pytest.raises(ValueError):
        page(51, maximum=50)
