"""Translation from Chinese to English and Russian using deep_translator."""

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from deep_translator import GoogleTranslator


@lru_cache(maxsize=512)
def translate_to_english(text: str) -> str:
    try:
        return GoogleTranslator(source="zh-CN", target="en").translate(text) or ""
    except Exception:
        return ""


@lru_cache(maxsize=512)
def translate_to_russian(text: str) -> str:
    try:
        return GoogleTranslator(source="zh-CN", target="ru").translate(text) or ""
    except Exception:
        return ""


def get_translations(
    text: str,
    *,
    need_en: bool = True,
    need_ru: bool = True,
) -> dict[str, str]:
    """Return {"en": ..., "ru": ...} translations for *text*.

    Only requests languages that are needed (faster when one side is off).
    """
    if need_en and need_ru:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_en = ex.submit(translate_to_english, text)
            f_ru = ex.submit(translate_to_russian, text)
            return {"en": f_en.result(), "ru": f_ru.result()}
    if need_en:
        return {"en": translate_to_english(text), "ru": ""}
    if need_ru:
        return {"en": "", "ru": translate_to_russian(text)}
    return {"en": "", "ru": ""}
