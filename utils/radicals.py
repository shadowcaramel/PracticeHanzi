"""Kangxi / Unihan radical lookup for optional PDF captions (Unicode Unihan kRSUnicode)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from functools import lru_cache
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "radicals"
KRS_CACHE = DATA_DIR / "krs_bmp_cache.json"
UNIHAN_ZIP = DATA_DIR / "Unihan.zip"
UNIHAN_ZIP_URL = "https://www.unicode.org/Public/zipped/16.0.0/Unihan.zip"

# Unicode Kangxi radical presentation forms: U+2F00 .. U+2FD3 (214 radicals).
_KANGXI_BASE = 0x2F00

_krs_line_re = re.compile(r"^U\+([0-9A-F]{4,6})\tkRSUnicode\t(.+)$")


def kangxi_radical_char(radical_index: int) -> str | None:
    """Return the Kangxi radical presentation character (1..214)."""
    if not (1 <= radical_index <= 214):
        return None
    return chr(_KANGXI_BASE + radical_index - 1)


def _build_krs_from_zip(zip_bytes: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    raw = zf.read("Unihan_IRGSources.txt").decode("utf-8", errors="replace")
    for line in raw.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        m = _krs_line_re.match(line)
        if not m:
            continue
        cp = int(m.group(1), 16)
        if 0x4E00 <= cp <= 0x9FFF:
            out[f"U+{m.group(1)}"] = m.group(2).strip()
    return out


def _ensure_krs_cache() -> dict[str, str]:
    """Map U+XXXX string -> kRSUnicode value (e.g. ``75.3``). BMP CJK Unified Ideographs only."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if KRS_CACHE.exists():
        return json.loads(KRS_CACHE.read_text(encoding="utf-8"))

    try:
        if not UNIHAN_ZIP.exists():
            resp = requests.get(UNIHAN_ZIP_URL, timeout=180)
            resp.raise_for_status()
            UNIHAN_ZIP.write_bytes(resp.content)

        out = _build_krs_from_zip(UNIHAN_ZIP.read_bytes())
    except Exception:
        out = {}

    KRS_CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


@lru_cache(maxsize=4096)
def radical_info(char: str) -> dict[str, str | int | None] | None:
    """Return radical metadata for a single CJK character, or None if unknown."""
    if len(char) != 1:
        return None
    cp = ord(char)
    if not (0x4E00 <= cp <= 0x9FFF):
        return None

    krs_map = _ensure_krs_cache()
    key = f"U+{cp:04X}"
    raw = krs_map.get(key)
    if not raw:
        return None

    parts = raw.replace("'", ".").split(".")
    if len(parts) < 2:
        return None
    try:
        radical_index = int(parts[0])
        strokes_after = int(parts[1])
    except ValueError:
        return None

    rchar = kangxi_radical_char(radical_index)
    return {
        "radical_index": radical_index,
        "radical_char": rchar,
        "strokes_after_radical": strokes_after,
        "krs": raw,
    }


def radical_caption(char: str) -> str | None:
    """One-line caption for PDF, e.g. ``部首: ⼥ (38+3)``."""
    info = radical_info(char)
    if not info or not info.get("radical_char"):
        return None
    ri = info["radical_index"]
    sa = info["strokes_after_radical"]
    return f"部首: {info['radical_char']} ({ri}+{sa})"
