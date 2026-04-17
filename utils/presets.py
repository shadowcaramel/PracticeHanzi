"""Bundled word-list presets (JSON) and optional HSK vocabulary (downloaded)."""

from __future__ import annotations

import json
import random
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
PRESETS_DIR = BASE_DIR / "data" / "presets"
HSK_DIR = BASE_DIR / "data" / "hsk"

# MIT — drkameleon/complete-hsk-vocabulary (new HSK 3.0 inclusive lists).
HSK_INCLUSIVE_NEW_URL = (
    "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/main/"
    "wordlists/inclusive/new/{level}.json"
)


def list_preset_names() -> list[str]:
    """Return preset ids (filenames without ``.json``) sorted."""
    if not PRESETS_DIR.is_dir():
        return []
    names: list[str] = []
    for p in sorted(PRESETS_DIR.glob("*.json")):
        names.append(p.stem)
    return names


def _normalize_entries(raw: object) -> list[str]:
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            zh = item.get("zh") or item.get("simplified")
            if isinstance(zh, str) and zh.strip():
                out.append(zh.strip())
    return out


def load_preset(name: str) -> list[str]:
    """Load a bundled preset by id (``numbers``, ``animals``, …)."""
    path = PRESETS_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Unknown preset: {name}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_entries(raw)


def ensure_hsk_level_file(level: int) -> Path:
    """Download HSK 3.0 inclusive word list for *level* (1–7) into ``data/hsk/`` if missing."""
    if level < 1 or level > 7:
        raise ValueError("HSK level must be between 1 and 7 (7 = levels 7–9 band in source data).")

    HSK_DIR.mkdir(parents=True, exist_ok=True)
    dest = HSK_DIR / f"hsk30_inclusive_new_{level}.json"
    if dest.exists():
        return dest

    url = HSK_INCLUSIVE_NEW_URL.format(level=level)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def load_hsk_simplified_words(level: int) -> list[str]:
    """Return all *simplified* headwords for the given HSK (3.0 new) inclusive level."""
    path = ensure_hsk_level_file(level)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    words: list[str] = []
    for entry in raw:
        if isinstance(entry, dict) and isinstance(entry.get("simplified"), str):
            w = entry["simplified"].strip()
            if w:
                words.append(w)
    return words


def sample_hsk_words(
    level: int,
    count: int,
    *,
    randomize: bool = False,
) -> list[str]:
    """Take up to *count* words from an HSK level (random or first *n* by list order)."""
    words = load_hsk_simplified_words(level)
    if not words:
        return []
    if count >= len(words):
        out = list(words)
    elif randomize:
        out = random.sample(words, count)
    else:
        out = words[:count]
    return out
