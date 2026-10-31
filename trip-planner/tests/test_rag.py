import requests

from utils import rag


def test_wikivoyage_returns_page_extract(monkeypatch):
    monkeypatch.setattr(
        rag,
        "_request_wikivoyage",
        lambda destination: {
            "query": {"pages": {"1": {"extract": "Local travel guide."}}}
        },
    )
    rag._cached_context.cache_clear()

    assert rag.get_destination_context("Seattle") == {
        "available": True,
        "context": "Local travel guide.",
    }


def test_wikivoyage_failure_returns_optional_fallback(monkeypatch):
    def fail_request(destination):
        raise requests.ConnectionError("unavailable")

    monkeypatch.setattr(rag, "_request_wikivoyage", fail_request)
    rag._cached_context.cache_clear()

    assert rag.get_destination_context("Seattle") == {
        "available": False,
        "context": "",
    }
