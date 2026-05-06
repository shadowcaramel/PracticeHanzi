"""Translation cache shape and API smoke checks."""

from unittest.mock import patch

import pytest

from utils import translation as tr


def test_secondary_translation_prefix() -> None:
    assert tr.secondary_translation_prefix("ru") == "RU"
    assert tr.secondary_translation_prefix("ja") == "JA"


def test_get_translations_skips_secondary_when_none() -> None:
    with patch.object(tr, "translate_to_english", return_value="hello"):
        out = tr.get_translations("测试", need_en=True, secondary_lang=None)
    assert out["en"] == "hello"
    assert out["secondary"] == ""


def test_get_translations_secondary_only_mocked() -> None:
    with (
        patch.object(tr, "translate_to_english", return_value=""),
        patch.object(tr, "translate_to_target", return_value="привет"),
    ):
        out = tr.get_translations("测试", need_en=False, secondary_lang="ru")
    assert out["en"] == ""
    assert out["secondary"] == "привет"


def test_translate_to_target_rejects_unknown_code() -> None:
    assert tr.translate_to_target("你好", "xx") == ""
