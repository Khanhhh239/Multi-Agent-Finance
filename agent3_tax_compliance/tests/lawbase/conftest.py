"""Lawbase tests run on small temporary corpora: the cross-encoder reranker (a 2 GB model) is not loaded here."""
import pytest

from src.lawbase.store import Corpus


@pytest.fixture(autouse=True)
def _no_reranker(monkeypatch):
    monkeypatch.setattr(Corpus, 'rerank', False)
