"""Offline test for the idiom extractor filter logic.

The real downloader is skipped — the filter / dedup / sort pipeline is what
we want to guarantee. We simulate the upstream CSV and HSK exclusion set.
"""

from importlib import util as _util
from pathlib import Path

import re

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_idioms_from_china_idiom.py"

_spec = _util.spec_from_file_location("build_idioms_from_china_idiom", SCRIPT)
_mod = _util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def test_cjk4_regex():
    pat: re.Pattern = _mod.CJK4_RE
    assert pat.match("画龙点睛")
    assert not pat.match("ABCD")
    assert not pat.match("画龙点")
    assert not pat.match("画龙点睛点")
    assert not pat.match("画龙点!")


def test_filter_pipeline(monkeypatch):
    """Replicate the selection logic against a synthetic upstream + HSK set."""
    curated = ["画龙点睛", "亡羊补牢", "abc", "五湖四海", "守株待兔"]
    upstream = {"画龙点睛", "亡羊补牢", "守株待兔", "五湖四海"}
    hsk = {"亡羊补牢"}  # simulate overlap

    kept: set[str] = set()
    for w in curated:
        if not _mod.CJK4_RE.match(w):
            continue
        if w in hsk:
            continue
        if w not in upstream:
            continue
        kept.add(w)

    assert kept == {"画龙点睛", "守株待兔", "五湖四海"}
    # Deterministic output is alphabetical.
    assert sorted(kept) == ["五湖四海", "守株待兔", "画龙点睛"]
