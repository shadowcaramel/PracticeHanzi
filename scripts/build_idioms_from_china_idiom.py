"""Build data/presets/idioms.json from sfyc23/China-idiom (MIT).

Deterministic, one-shot extractor. Run once by the maintainer:

    python scripts/build_idioms_from_china_idiom.py

Approach
--------
The upstream CSV does not carry a true frequency / popularity column
(``next_count`` counts possible 接龙 successors, so it skews toward obscure
idioms whose endings can start many others). To keep the bundled word bank
useful for learners, we use a **curated whitelist** of widely-known chengyu
and **validate** each entry exists in the upstream MIT-licensed CSV before
writing it out. Entries that are also present in cached HSK lists are
dropped so the Idioms bank does not overlap with HSK practice. The final
list is saved sorted alphabetically so rebuilds are deterministic.

Upstream: https://github.com/sfyc23/China-idiom (MIT License).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
PRESETS_DIR = REPO_ROOT / "data" / "presets"
CACHE_DIR = REPO_ROOT / "data" / "mmh_idioms"
CSV_URL = "https://raw.githubusercontent.com/sfyc23/China-idiom/master/china_idiom/idiom.csv"
CSV_PATH = CACHE_DIR / "idiom.csv"
OUT_PATH = PRESETS_DIR / "idioms.json"

CJK4_RE = re.compile(r"^[\u4e00-\u9fff]{4}$")

# Curated pedagogical whitelist of well-known 4-character chengyu
# (high learner value; widely-attested; mostly concrete imagery). All entries
# are validated against sfyc23/China-idiom on build so the file remains a
# bona-fide subset of an MIT-licensed corpus.
CURATED_IDIOMS: list[str] = [
    "一举两得", "一心一意", "一帆风顺", "一目了然", "一见钟情",
    "一鸣惊人", "一丝不苟", "一日千里", "一言为定", "一成不变",
    "画龙点睛", "画蛇添足", "画饼充饥",
    "守株待兔", "刻舟求剑", "亡羊补牢", "愚公移山", "塞翁失马",
    "指鹿为马", "对牛弹琴",
    "井底之蛙", "叶公好龙", "杯弓蛇影", "杞人忧天",
    "自相矛盾", "南辕北辙", "狐假虎威",
    "三心二意", "七上八下", "九牛一毛", "十全十美",
    "千变万化", "千军万马", "千方百计",
    "半途而废", "半信半疑",
    "同甘共苦", "同舟共济",
    "心旷神怡", "心满意足", "心想事成", "心平气和", "心灰意冷",
    "精益求精", "全力以赴", "兢兢业业", "孜孜不倦",
    "温故知新", "青出于蓝", "名副其实", "名正言顺",
    "不可思议", "不劳而获", "不知所措", "不言而喻",
    "实事求是", "脚踏实地", "循序渐进",
    "日新月异", "日积月累",
    "络绎不绝", "如鱼得水", "津津有味",
    "风和日丽", "风调雨顺",
    "山清水秀", "水落石出", "水到渠成",
    "大同小异", "大材小用", "小题大做",
    "出人意料", "出类拔萃", "出神入化",
    "因材施教", "言行一致",
    "喜出望外", "喜闻乐见",
    "马到成功", "马马虎虎",
]


def _download_csv() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CSV_PATH.exists() and CSV_PATH.stat().st_size > 100_000:
        return CSV_PATH
    print(f"[info] downloading {CSV_URL}")
    resp = requests.get(CSV_URL, timeout=180)
    resp.raise_for_status()
    CSV_PATH.write_bytes(resp.content)
    return CSV_PATH


def _inspect_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, [])
    print(f"[info] csv header ({len(header)} cols): {header}")
    return header


def _load_upstream_words(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if "word" not in (reader.fieldnames or []):
            raise SystemExit(
                f"CSV schema changed: expected a 'word' column, got {reader.fieldnames}. "
                "Adjust the field map in scripts/build_idioms_from_china_idiom.py."
            )
        out: set[str] = set()
        for row in reader:
            w = (row.get("word") or "").strip()
            if w:
                out.add(w)
        return out


def _load_hsk_exclusions() -> set[str]:
    """Best-effort: read any HSK JSON already cached on disk and return words to skip."""
    hsk_dir = REPO_ROOT / "data" / "hsk"
    excl: set[str] = set()
    if not hsk_dir.is_dir():
        return excl
    for p in sorted(hsk_dir.glob("hsk30_inclusive_new_*.json")):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[warn] could not read {p.name}: {exc}")
            continue
        if not isinstance(raw, list):
            continue
        for entry in raw:
            if isinstance(entry, dict):
                w = entry.get("simplified")
                if isinstance(w, str) and w.strip():
                    excl.add(w.strip())
    return excl


def build() -> None:
    csv_path = _download_csv()
    _inspect_header(csv_path)
    upstream = _load_upstream_words(csv_path)
    print(f"[info] upstream corpus: {len(upstream)} entries")
    excl = _load_hsk_exclusions()
    if excl:
        print(f"[info] loaded {len(excl)} HSK words to deduplicate against")

    missing: list[str] = []
    bad_shape: list[str] = []
    dropped_hsk: list[str] = []
    kept: set[str] = set()
    for w in CURATED_IDIOMS:
        if not CJK4_RE.match(w):
            bad_shape.append(w)
            continue
        if w in excl:
            dropped_hsk.append(w)
            continue
        if w not in upstream:
            missing.append(w)
            continue
        kept.add(w)

    if bad_shape:
        print(f"[warn] {len(bad_shape)} curated entries failed len==4 CJK check: {bad_shape}")
    if dropped_hsk:
        print(f"[info] {len(dropped_hsk)} curated entries overlap HSK (dropped): {dropped_hsk}")
    if missing:
        print(f"[warn] {len(missing)} curated entries not in upstream CSV: {missing}")

    if not kept:
        raise SystemExit("No curated idioms validated against the upstream CSV.")

    picked = sorted(kept)
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(picked, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[ok] wrote {len(picked)} idioms to {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    try:
        build()
    except requests.RequestException as exc:
        print(f"[error] network failure: {exc}", file=sys.stderr)
        raise SystemExit(2)
