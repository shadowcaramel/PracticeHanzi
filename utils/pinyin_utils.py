"""Pinyin transcription helper using pypinyin."""

from pypinyin import pinyin, Style


def get_pinyin(text: str) -> str:
    """Return tone-marked pinyin string for the given Chinese text.

    Example: "你好" -> "nǐ hǎo"
    """
    result = pinyin(text, style=Style.TONE, errors="ignore")
    return " ".join(syllable[0] for syllable in result if syllable[0])


def get_pinyin_per_char(text: str) -> list[tuple[str, str]]:
    """Return list of (character, pinyin) pairs.

    Non-CJK characters get an empty pinyin string.
    """
    result = pinyin(text, style=Style.TONE, errors="ignore")
    pairs = []
    for ch, py in zip(text, result):
        pairs.append((ch, py[0] if py else ""))
    return pairs
