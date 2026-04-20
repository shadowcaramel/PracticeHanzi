"""Offline tests for utils.decomposition using a tiny in-memory fixture."""

from unittest.mock import patch

from utils import decomposition as dec


FIXTURE = {
    "妈": {
        "character": "妈",
        "decomposition": "\u2ff0女马",
        "etymology": {
            "type": "pictophonetic",
            "hint": "female",
            "semantic": "女",
            "phonetic": "马",
        },
    },
    "马": {
        "character": "马",
        "decomposition": "\u2ff0马",
        "definition": "horse",
    },
    "木": {
        "character": "木",
        "decomposition": "?",
        "etymology": {"type": "pictographic", "hint": "tree"},
    },
}


def _fake_table():
    return FIXTURE


def test_ids_compact_known(monkeypatch):
    monkeypatch.setattr(dec, "_mmh_table", _fake_table)
    assert dec.ids_compact("妈") == "\u2ff0女马"


def test_ids_compact_question_mark_returns_none(monkeypatch):
    monkeypatch.setattr(dec, "_mmh_table", _fake_table)
    assert dec.ids_compact("木") is None


def test_ids_compact_missing(monkeypatch):
    monkeypatch.setattr(dec, "_mmh_table", _fake_table)
    assert dec.ids_compact("X") is None


def test_decomposition_lines_pictophonetic(monkeypatch):
    monkeypatch.setattr(dec, "_mmh_table", _fake_table)
    lines = dec.decomposition_lines("妈")
    assert any("left-right" in l for l in lines)
    assert any("semantic" in l for l in lines)
    assert any("phonetic" in l for l in lines)


def test_decomposition_lines_empty_for_unknown(monkeypatch):
    monkeypatch.setattr(dec, "_mmh_table", _fake_table)
    assert dec.decomposition_lines("Z") == []


def test_decomposition_lines_question_mark(monkeypatch):
    monkeypatch.setattr(dec, "_mmh_table", _fake_table)
    # "?" structure is treated as unknown, returns [].
    assert dec.decomposition_lines("木") == []
