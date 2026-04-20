"""Chinese-to-English/Russian translation with disk-persistent cache.

Design notes
------------
* ``GoogleTranslator`` calls dominate PDF-generation time; the upstream
  ``deep-translator`` client has no batch endpoint, so we parallelize with a
  module-level ``ThreadPoolExecutor`` reused across calls.
* Results are memoized in-process (``functools.lru_cache``) and mirrored to
  ``data/translation_cache.json``. The JSON is loaded on first import and
  flushed on ``atexit`` so repeated PDF generations of overlapping HSK
  vocabulary never re-hit the network.
* A single 0.5s backoff retry smooths transient failures. Empty strings are
  still the "no translation" signal for the PDF generator.
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

_LRU_MAX = 4096
_RETRY_SLEEP_S = 0.5

_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="xlate")
_cache_lock = threading.Lock()
_dirty = False


def _load_cache() -> tuple[dict[str, str], dict[str, str]]:
    if not CACHE_FILE.is_file():
        return {}, {}
    try:
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}
    en = raw.get("en") if isinstance(raw, dict) else None
    ru = raw.get("ru") if isinstance(raw, dict) else None
    return (en if isinstance(en, dict) else {}, ru if isinstance(ru, dict) else {})


_EN_SEED, _RU_SEED = _load_cache()


def _persist() -> None:
    """Flush cached translations to disk (called at shutdown)."""
    global _dirty
    with _cache_lock:
        if not _dirty:
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(
                json.dumps({"en": _en_values, "ru": _ru_values}, ensure_ascii=False),
                encoding="utf-8",
            )
            _dirty = False
        except Exception:
            pass


_en_values: dict[str, str] = dict(_EN_SEED)
_ru_values: dict[str, str] = dict(_RU_SEED)


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
def translate_to_russian(text: str) -> str:
    if not text:
        return ""
    cached = _ru_values.get(text)
    if cached is not None:
        return cached
    out = _retry(GoogleTranslator(source="zh-CN", target="ru").translate, text) or ""
    global _dirty
    with _cache_lock:
        _ru_values[text] = out
        _dirty = True
    return out


def get_translations(
    text: str,
    *,
    need_en: bool = True,
    need_ru: bool = True,
) -> dict[str, str]:
    """Return ``{"en": ..., "ru": ...}`` for *text*; skipped langs return ""."""
    if need_en and need_ru:
        f_en = _pool.submit(translate_to_english, text)
        f_ru = _pool.submit(translate_to_russian, text)
        return {"en": f_en.result(), "ru": f_ru.result()}
    if need_en:
        return {"en": translate_to_english(text), "ru": ""}
    if need_ru:
        return {"en": "", "ru": translate_to_russian(text)}
    return {"en": "", "ru": ""}


def prefetch_translations(
    texts: Iterable[str],
    *,
    need_en: bool,
    need_ru: bool,
) -> None:
    """Parallel-warm the translation caches for every string in *texts*.

    Safe to call even when both flags are False (it becomes a no-op).
    """
    if not (need_en or need_ru):
        return
    uniq = {t for t in texts if t}
    if not uniq:
        return
    futs = []
    for t in uniq:
        if need_en:
            futs.append(_pool.submit(translate_to_english, t))
        if need_ru:
            futs.append(_pool.submit(translate_to_russian, t))
    for f in futs:
        try:
            f.result()
        except Exception:
            pass
    _persist()


def save_translation_cache_now() -> None:
    """Public flush entry point (used by the PDF generator after each job)."""
    _persist()
