import numpy as np
import requests

from utils.providers import rag


class Encoder:
    def encode(self, texts, normalize_embeddings=True, **kwargs):
        return np.array([
            [1.0, 0.0] if "beach" in text.casefold() else [0.0, 1.0]
            for text in texts
        ])


def test_semantic_vectors_select_relevant_passage_not_article_prefix(monkeypatch):
    monkeypatch.setattr(rag, "_encoder", lambda: Encoder())
    monkeypatch.setattr(
        rag, "_request_wikivoyage",
        lambda destination: {"query": {"pages": {"1": {"extract": "Museum " * 180 + "Beach coast " * 100}}}},
    )
    rag._cached_context.cache_clear()
    rag._index.cache_clear()
    result = rag.get_destination_context("Seattle", query="beach")
    assert result["available"]
    assert "Beach" in result["passages"][0]["text"]
    assert result["passages"][0]["score"] == 1
    assert result["passages"][0]["url"].endswith("/Seattle")
    assert len(result["context"]) <= 3000


def test_wikivoyage_failure_returns_explicit_optional_fallback(monkeypatch):
    def fail(destination):
        raise requests.ConnectionError("unavailable")

    monkeypatch.setattr(rag, "_request_wikivoyage", fail)
    rag._cached_context.cache_clear()
    result = rag.get_destination_context("Seattle", query="beach")
    assert not result["available"]
    assert result["context"] == ""
    assert result["passages"] == []
    assert result["reason"]
