from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
import string
import unicodedata


class TextQualityStatus(StrEnum):
    VALID = "valid"
    EMPTY = "empty"
    TOO_SHORT = "too_short"
    GARBLED = "garbled"
    BINARY_LIKE = "binary_like"


@dataclass(frozen=True, slots=True)
class TextQualityReport:
    status: TextQualityStatus
    sanitized_text: str
    character_count: int
    meaningful_character_count: int
    control_character_count: int
    control_character_ratio: float
    readable_character_ratio: float


INLINE_WHITESPACE_PATTERN = re.compile(r"[^\S\n]+")
MAX_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")
MIN_MEANINGFUL_CHARACTERS = 4
MIN_READABLE_RATIO = 0.35
MAX_CONTROL_RATIO = 0.02
READABLE_PUNCTUATION = set(string.punctuation) | set("，。！？；：、“”‘’（）《》【】—…·￥")


def sanitize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    characters: list[str] = []
    for character in normalized:
        if character == "\x00":
            continue
        if character == "\n":
            characters.append(character)
            continue
        if _is_control_character(character):
            continue
        characters.append(character)

    without_controls = "".join(characters)
    compacted_lines = [
        INLINE_WHITESPACE_PATTERN.sub(" ", line).strip()
        for line in without_controls.split("\n")
    ]
    compacted = "\n".join(compacted_lines).strip()
    return MAX_BLANK_LINES_PATTERN.sub("\n\n", compacted)


def detect_text_quality(text: str) -> TextQualityReport:
    sanitized = sanitize_text(text)
    raw_count = len(text)
    control_count = sum(
        1
        for character in text
        if character != "\x00" and character not in {"\n", "\r", "\t"} and _is_control_character(character)
    )
    control_ratio = control_count / raw_count if raw_count else 0.0

    if "\x00" in text:
        status = TextQualityStatus.BINARY_LIKE
    elif not sanitized.strip():
        status = TextQualityStatus.EMPTY
    else:
        visible_characters = [character for character in sanitized if not character.isspace()]
        visible_count = len(visible_characters)
        meaningful_count = sum(1 for character in visible_characters if character.isalnum())
        readable_count = sum(1 for character in visible_characters if _is_readable_character(character))
        readable_ratio = readable_count / visible_count if visible_count else 0.0

        if control_ratio > MAX_CONTROL_RATIO:
            status = TextQualityStatus.GARBLED
        elif visible_count >= 12 and readable_ratio < MIN_READABLE_RATIO:
            status = TextQualityStatus.GARBLED
        elif meaningful_count < MIN_MEANINGFUL_CHARACTERS:
            status = TextQualityStatus.TOO_SHORT
        else:
            status = TextQualityStatus.VALID

        return TextQualityReport(
            status=status,
            sanitized_text=sanitized,
            character_count=len(sanitized),
            meaningful_character_count=meaningful_count,
            control_character_count=control_count,
            control_character_ratio=control_ratio,
            readable_character_ratio=readable_ratio,
        )

    return TextQualityReport(
        status=status,
        sanitized_text=sanitized,
        character_count=len(sanitized),
        meaningful_character_count=sum(1 for character in sanitized if character.isalnum()),
        control_character_count=control_count,
        control_character_ratio=control_ratio,
        readable_character_ratio=0.0,
    )


def _is_control_character(character: str) -> bool:
    return unicodedata.category(character).startswith("C")


def _is_readable_character(character: str) -> bool:
    return (
        character.isalnum()
        or character in READABLE_PUNCTUATION
        or unicodedata.category(character).startswith(("L", "N", "P"))
    )
