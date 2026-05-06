"""Chinese-to-multilingual translation with disk-persistent cache.

Uses ``deep_translator.GoogleTranslator`` (machine translation; accuracy varies).
Results are memoized in-process (``functools.lru_cache``) and mirrored to
``data/translation_cache.json``.
"""

from __future__ import annotations

import atexit
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from deep_translator import GoogleTranslator

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "data"
CACHE_FILE = CACHE_DIR / "translation_cache.json"

# Allowed Google Translate target codes (zh-CN → target); avoids arbitrary cache keys.
SECONDARY_TRANSLATION_TARGETS: tuple[str, ...] = (
    "ru",
    "ja",
    "ko",
    "fr",
    "de",
    "es",
    "it",
    "pt",
    "vi",
    "th",
    "id",
    "ar",
    "hi",
    "pl",
    "uk",
    "tr",
)

SECONDARY_TRANSLATION_LABELS: dict[str, str] = {
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ar": "Arabic",
    "hi": "Hindi",
    "pl": "Polish",
    "uk": "Ukrainian",
    "tr": "Turkish",
}


def secondary_translation_prefix(lang: str) -> str:
    """PDF column prefix (e.g. ``JA`` for Japanese)."""
    return lang.strip().lower()[:2].upper() if lang else ""


_LRU_MAX = 4096
_RETRY_SLEEP_S = 0.5

_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="xlate")
_cache_lock = threading.Lock()
_dirty = False


def _migrate_legacy_payload(raw: dict) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Return ``(en_map, by_target)`` from raw JSON, migrating legacy ``ru`` top-level."""
    en = raw.get("en") if isinstance(raw, dict) else None
    en_map = en if isinstance(en, dict) else {}

    by_target: dict[str, dict[str, str]] = {}
    bt = raw.get("by_target") if isinstance(raw, dict) else None
    if isinstance(bt, dict):
        for k, v in bt.items():
            if isinstance(k, str) and isinstance(v, dict):
                by_target[k] = dict(v)

    legacy_ru = raw.get("ru") if isinstance(raw, dict) else None
    if isinstance(legacy_ru, dict) and legacy_ru:
        existing = by_target.setdefault("ru", {})
        for text, val in legacy_ru.items():
            if text not in existing:
                existing[str(text)] = str(val) if val is not None else ""

    return dict(en_map), by_target


def _load_cache() -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    if not CACHE_FILE.is_file():
        return {}, {}
    try:
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}
    if not isinstance(raw, dict):
        return {}, {}
    return _migrate_legacy_payload(raw)


_EN_SEED, _BY_TARGET_SEED = _load_cache()


def _persist() -> None:
    global _dirty
    with _cache_lock:
        if not _dirty:
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"en": _en_values, "by_target": _by_target_values}
            CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            _dirty = False
        except Exception:
            pass


_en_values: dict[str, str] = dict(_EN_SEED)
_by_target_values: dict[str, dict[str, str]] = {
    k: dict(v) for k, v in _BY_TARGET_SEED.items()
}


atexit.register(_persist)


def _retry(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except Exception:
        time.sleep(_RETRY_SLEEP_S)
        try:
            return fn(*args, **kw)
        except Exception:
            return None


def _target_bucket(lang: str) -> dict[str, str]:
    code = lang.strip().lower()
    if code not in SECONDARY_TRANSLATION_TARGETS:
        return {}
    if code not in _by_target_values:
        _by_target_values[code] = {}
    return _by_target_values[code]


@lru_cache(maxsize=_LRU_MAX)
def translate_to_english(text: str) -> str:
    if not text:
        return ""
    cached = _en_values.get(text)
    if cached is not None:
        return cached
    out = _retry(GoogleTranslator(source="zh-CN", target="en").translate, text) or ""
    global _dirty
    with _cache_lock:
        _en_values[text] = out
        _dirty = True
    return out


@lru_cache(maxsize=_LRU_MAX)
def translate_to_target(text: str, target: str) -> str:
    """Translate *text* to *target* (must be in ``SECONDARY_TRANSLATION_TARGETS``)."""
    if not text:
        return ""
    tgt = target.strip().lower()
    if tgt not in SECONDARY_TRANSLATION_TARGETS:
        return ""
    bucket = _target_bucket(tgt)
    cached = bucket.get(text)
    if cached is not None:
        return cached
    out = _retry(GoogleTranslator(source="zh-CN", target=tgt).translate, text) or ""
    global _dirty
    with _cache_lock:
        bucket[text] = out
        _dirty = True
    return out


def get_translations(
    text: str,
    *,
    need_en: bool = True,
    secondary_lang: str | None = None,
) -> dict[str, str]:
    """Return ``{"en": ..., "secondary": ...}``; skipped entries are ``""``.

    *secondary_lang* must be ``None`` or an allowlisted target code.
    """
    sec = None
    if secondary_lang and secondary_lang.strip().lower() in SECONDARY_TRANSLATION_TARGETS:
        sec = secondary_lang.strip().lower()

    if need_en and sec:
        f_en = _pool.submit(translate_to_english, text)
        f_s = _pool.submit(translate_to_target, text, sec)
        return {"en": f_en.result(), "secondary": f_s.result()}
    if need_en:
        return {"en": translate_to_english(text), "secondary": ""}
    if sec:
        return {"en": "", "secondary": translate_to_target(text, sec)}
    return {"en": "", "secondary": ""}


def prefetch_translations(
    texts: Iterable[str],
    *,
    need_en: bool,
    secondary_lang: str | None,
) -> None:
    if not (need_en or secondary_lang):
        return
    sec = None
    if secondary_lang and secondary_lang.strip().lower() in SECONDARY_TRANSLATION_TARGETS:
        sec = secondary_lang.strip().lower()
    if not (need_en or sec):
        return
    uniq = {t for t in texts if t}
    if not uniq:
        return
    futs = []
    for t in uniq:
        if need_en:
            futs.append(_pool.submit(translate_to_english, t))
        if sec:
            futs.append(_pool.submit(translate_to_target, t, sec))
    for f in futs:
        try:
            f.result()
        except Exception:
            pass
    _persist()


def save_translation_cache_now() -> None:
    """Public flush entry point (used by the PDF generator after each job)."""
    _persist()


# Back-compat for tests / external callers
def translate_to_russian(text: str) -> str:
    return translate_to_target(text, "ru")
