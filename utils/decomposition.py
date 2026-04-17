"""IDS and etymology lines from Make Me a Hanzi ``dictionary.txt`` (LGPL v3+; see project COPYING)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "mmh"
DICT_FILE = DATA_DIR / "dictionary.txt"
DICT_URL = "https://cdn.jsdelivr.net/gh/skishore/makemeahanzi@master/dictionary.txt"

# Unicode Ideographic Description Characters (subset used in MMH data).
_IDS_NAMES: dict[str, str] = {
    "\u2ff0": "left-right",
    "\u2ff1": "top-bottom",
    "\u2ff2": "left-center-right",
    "\u2ff3": "top-center-bottom",
    "\u2ff4": "full surround",
    "\u2ff5": "surround from above",
    "\u2ff6": "surround from below",
    "\u2ff7": "surround from left",
    "\u2ff8": "surround from upper left",
    "\u2ff9": "surround from upper right",
    "\u2ffa": "surround from lower left",
    "\u2ffb": "overlaid",
}

def _truncate(s: str, max_len: int = 110) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _ids_layout_word(decomposition: str) -> str | None:
    if not decomposition:
        return None
    first = decomposition[0]
    return _IDS_NAMES.get(first)


def _load_table() -> dict[str, dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DICT_FILE.exists():
        try:
            resp = requests.get(DICT_URL, timeout=120)
            resp.raise_for_status()
            DICT_FILE.write_bytes(resp.content)
        except Exception:
            return {}

    raw = DICT_FILE.read_text(encoding="utf-8", errors="replace")
    out: dict[str, dict] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ch = obj.get("character")
        if not isinstance(ch, str) or len(ch) != 1:
            continue
        out[ch] = obj
    return out


@lru_cache(maxsize=1)
def _mmh_table() -> dict[str, dict]:
    return _load_table()


def ensure_decomposition_data() -> None:
    """Warm the MMH dictionary cache (used before PDF generation when decomposition is on)."""
    _mmh_table()


def mmh_entry(char: str) -> dict | None:
    """Return the raw dictionary entry for *char*, or None."""
    if len(char) != 1:
        return None
    return _mmh_table().get(char)


def ids_compact(char: str) -> str | None:
    """Return a short IDS string (no ``IDS:`` prefix) for under-glyph captions, or None."""
    entry = mmh_entry(char)
    if not entry:
        return None
    dec = (entry.get("decomposition") or "").strip()
    if not dec or dec[0] in ("？", "?"):
        return None
    return dec


def decomposition_lines(char: str) -> list[str]:
    """Return 1–2 short lines: IDS (+ layout), then etymology / roles when available."""
    entry = mmh_entry(char)
    if not entry:
        return []

    dec = (entry.get("decomposition") or "").strip()
    # MMH marks unknown structure with a lone question mark (often fullwidth).
    if not dec or dec[0] in ("？", "?"):
        return []

    layout = _ids_layout_word(dec)
    if layout:
        lines = [_truncate(f"IDS: {dec} ({layout})")]
    else:
        lines = [_truncate(f"IDS: {dec}")]

    et = entry.get("etymology")
    if not isinstance(et, dict):
        return lines

    etype = (et.get("type") or "").strip()
    hint = (et.get("hint") or "").strip()

    if etype == "pictophonetic":
        sem = (et.get("semantic") or "").strip()
        ph = (et.get("phonetic") or "").strip()
        parts: list[str] = []
        if sem:
            if hint:
                parts.append(f"{sem} (semantic: {hint})")
            else:
                parts.append(f"{sem} (semantic)")
        if ph:
            sub = mmh_entry(ph) or {}
            pdef = (sub.get("definition") or "").strip()
            if pdef:
                short = pdef.split(";")[0].strip()
                parts.append(f"{ph} (phonetic: {short})")
            else:
                parts.append(f"{ph} (phonetic)")
        if parts:
            lines.append(_truncate(" · ".join(parts)))
        return lines

    if etype == "ideographic" and hint:
        lines.append(_truncate(f"Ideographic: {hint}"))
    elif etype == "pictographic" and hint:
        lines.append(_truncate(f"Pictographic: {hint}"))
    elif hint:
        label = etype or "composition"
        lines.append(_truncate(f"{label}: {hint}"))

    return lines


def phrase_mmh_gloss(phrase: str) -> str | None:
    """Join short MMH English glosses per CJK character (semicolon-separated)."""
    parts: list[str] = []
    for ch in phrase:
        ent = mmh_entry(ch)
        if not ent:
            continue
        d = (ent.get("definition") or "").strip()
        if not d:
            continue
        short = d.split(";")[0].strip()
        if len(short) > 40:
            short = short[:39] + "…"
        parts.append(f"{ch} {short}")
    if not parts:
        return None
    return "MMH gloss: " + "; ".join(parts)
