from utils.pdf_naming import build_practice_hanzi_pdf_filename


def test_basic_cjk_slug():
    assert build_practice_hanzi_pdf_filename("你好") == "PracticeHanzi_你好.pdf"


def test_hsk_source():
    assert build_practice_hanzi_pdf_filename("你好", source=("hsk", 3)) == "PracticeHanzi_HSK3_L3_你好.pdf"


def test_preset_source():
    n = build_practice_hanzi_pdf_filename("你好", source=("preset", "animals"))
    assert n == "PracticeHanzi_preset_animals_你好.pdf"


def test_cjk_truncated_to_three():
    name = build_practice_hanzi_pdf_filename("一二三四五六七八九十")
    assert name == "PracticeHanzi_一二三.pdf"


def test_ascii_filename_uses_pinyin():
    out = build_practice_hanzi_pdf_filename("你好", ascii_only=True)
    assert out.endswith(".pdf")
    assert "你" not in out and "好" not in out
    assert "PracticeHanzi_" in out


def test_long_stem_capped():
    name = build_practice_hanzi_pdf_filename(
        "你好", source=("preset", "x" * 500)
    )
    assert len(name) <= 160 + len(".pdf")


def test_empty_text_fallback():
    assert build_practice_hanzi_pdf_filename("").endswith("_sheet.pdf")
