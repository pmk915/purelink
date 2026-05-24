from __future__ import annotations

import re


WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_entity_name(name: str) -> str:
    normalized = WHITESPACE_PATTERN.sub(" ", name.strip())
    return normalized.casefold()


def canonical_entity_name(name: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", name.strip())
