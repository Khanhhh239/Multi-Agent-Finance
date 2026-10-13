from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.utils import load_yaml


_WHITESPACE = re.compile(r"\s+")
_QUOTE_TRANSLATION = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_DASH_TRANSLATION = str.maketrans({"–": "-", "—": "-", "−": "-"})


def normalize_text(text: str, config: dict[str, Any] | None = None) -> str:
    settings = config or load_yaml("configs/normalization.yaml")
    value = unicodedata.normalize(settings.get("unicode_form", "NFC"), text or "")
    if settings.get("normalize_smart_quotes", True):
        value = value.translate(_QUOTE_TRANSLATION)
    if settings.get("normalize_dashes", True):
        value = value.translate(_DASH_TRANSLATION)
    if settings.get("collapse_whitespace", True):
        value = _WHITESPACE.sub(" ", value)
    if settings.get("strip", True):
        value = value.strip()
    if settings.get("casefold", False):
        value = value.casefold()
    return value


def accent_insensitive(text: str) -> str:
    value = unicodedata.normalize("NFD", normalize_text(text))
    return "".join(character for character in value if unicodedata.category(character) != "Mn").casefold()

