"""Injectable embedding providers, including a deterministic offline baseline."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from itertools import pairwise
from typing import Protocol, runtime_checkable

import numpy as np

WORD_RE = re.compile(r"[\w%]+", flags=re.UNICODE)


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold().strip()


def tokenize(text: str) -> list[str]:
    return WORD_RE.findall(normalize_text(text))


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbeddingProvider:
    """Dependency-free multilingual feature hashing for local reproducible tests.

    It is a baseline, not a replacement for a benchmarked multilingual model.
    Word features preserve Vietnamese diacritics and character n-grams give
    useful overlap for inflected or slightly misspelled phrases.
    """

    def __init__(self, dimensions: int = 768, name: str = "hashing-v1") -> None:
        if dimensions < 64:
            raise ValueError("dimensions must be at least 64")
        self.dimensions = dimensions
        self.name = name

    @property
    def model_id(self) -> str:
        return f"{self.name}:{self.dimensions}"

    def _features(self, text: str) -> list[str]:
        normalized = normalize_text(text)
        words = tokenize(normalized)
        features = [f"w:{word}" for word in words]
        features.extend(f"b:{left}_{right}" for left, right in pairwise(words))
        compact = re.sub(r"\s+", " ", normalized)
        for size in (3, 4, 5):
            features.extend(f"c:{compact[i:i + size]}" for i in range(len(compact) - size + 1))
        return features

    def _embed(self, text: str) -> list[float]:
        vector = np.zeros(self.dimensions, dtype=np.float64)
        for feature in self._features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "little")
            index = number % self.dimensions
            sign = 1.0 if number & 1 else -1.0
            vector[index] += sign
        norm = np.linalg.norm(vector)
        if norm:
            vector /= norm
        return vector.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]
