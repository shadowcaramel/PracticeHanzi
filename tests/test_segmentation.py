from utils.segmentation import (
    character_sequence,
    extract_cjk,
    infer_layout_mode,
    is_cjk,
    phrase_segments,
)


def test_is_cjk_ranges():
    assert is_cjk("中")
    assert is_cjk("永")
    assert not is_cjk("A")
    assert not is_cjk("")
    assert not is_cjk("AB")


def test_extract_cjk_strips_non_han():
    assert extract_cjk("Hello 你好!") == "你好"
    assert extract_cjk("") == ""
    assert extract_cjk("abc123") == ""


def test_phrase_segments_whitespace_split():
    assert phrase_segments("你好 谢谢") == ["你好", "谢谢"]
    assert phrase_segments("你好\n谢谢") == ["你好", "谢谢"]


def test_phrase_segments_single_run():
    # No whitespace → treat the whole thing as one phrase.
    assert phrase_segments("你好") == ["你好"]


def test_phrase_segments_ignores_punctuation():
    assert phrase_segments("你好! 再见?") == ["你好", "再见"]


def test_phrase_segments_empty():
    assert phrase_segments("") == []
    assert phrase_segments("   ") == []


def test_character_sequence_keeps_non_whitespace():
    assert character_sequence("你 好") == ["你", "好"]
    assert character_sequence("ab c") == ["a", "b", "c"]
    assert character_sequence("") == []


def test_infer_layout_mode():
    assert infer_layout_mode("你好 谢谢") == "phrase"
    assert infer_layout_mode("你好") == "character"
    assert infer_layout_mode("") == "character"
    assert infer_layout_mode("   ") == "character"
