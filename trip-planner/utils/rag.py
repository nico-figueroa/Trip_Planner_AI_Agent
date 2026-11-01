"""Optional, bounded Wikivoyage destination retrieval."""

from __future__ import annotations

import logging
import threading
from functools import lru_cache # Caching decorator to store recent results in memory
from typing import Any
from pathlib import Path
from urllib.parse import quote

import numpy as np

import requests # HTTP requests library for making API calls
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from utils.config import USER_AGENT, WIKIVOYAGE_API_URL, resolve_secret

logger = logging.getLogger(__name__)
MAX_CONTEXT_CHARS = 3000 # Maximum number of characters to retrieve from Wikivoyage extract
MAX_ARTICLE_CHARS = 80000
_model_lock = threading.Lock()


def prepare_model() -> None:
    """Administrator-only preparation downloads public weights without Hub credentials."""
    from sentence_transformers import SentenceTransformer

    model_path = resolve_secret("RAG_MODEL_PATH")[0] or str(
        Path(__file__).resolve().parents[2] / "models" / "all-MiniLM-L6-v2"
    )
    model = SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2", device="cpu",
        trust_remote_code=False, token=False,
    )
    model.save(model_path)
    with _model_lock:
        _load_encoder.cache_clear()
        _index.cache_clear()

# Determine if an error is retryable for Wikivoyage requests
def _is_retryable(error: BaseException) -> bool:
    if not isinstance(error, requests.RequestException):
        return False
    response = getattr(error, "response", None)
    return response is None or response.status_code == 429 or response.status_code >= 500

# Retry decorator for Wikivoyage requests
@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(2),
    reraise=True,
)

# Make a request to the Wikivoyage API with retry logic
def _request_wikivoyage(destination: str) -> dict[str, Any]:
    response = requests.get(
        WIKIVOYAGE_API_URL,
        params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "titles": destination,
            "format": "json",
            "redirects": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=(5, 15),
    )
    response.raise_for_status()
    return response.json()

# Cached wrapper around Wikivoyage context retrieval to reduce API calls
@lru_cache(maxsize=64) # Maximum of 64 cached results to limit memory usage
def _cached_context(destination: str) -> tuple[bool, str]:
    data = _request_wikivoyage(destination)
    if not isinstance(data, dict):
        raise ValueError("Wikivoyage returned an invalid response.")
    query = data.get("query", {})
    if not isinstance(query, dict):
        raise ValueError("Wikivoyage returned an invalid query result.")
    pages = query.get("pages", {})
    if not isinstance(pages, dict):
        raise ValueError("Wikivoyage returned an invalid page list.")
    page = next(iter(pages.values()), {})
    if not isinstance(page, dict):
        raise ValueError("Wikivoyage returned an invalid page.")
    extract = str(page.get("extract", "")).strip()[:MAX_ARTICLE_CHARS]
    return bool(extract), extract

@lru_cache(maxsize=1)
def _load_encoder() -> Any:
    """Load administrator-prepared weights locally, never remote Python code."""
    from sentence_transformers import SentenceTransformer

    model_path = resolve_secret("RAG_MODEL_PATH")[0] or str(
        Path(__file__).resolve().parents[2] / "models" / "all-MiniLM-L6-v2"
    )
    if not Path(model_path).is_dir():
        raise FileNotFoundError("Configure RAG_MODEL_PATH with a prepared semantic model directory.")
    return SentenceTransformer(
        model_path, device="cpu", local_files_only=True, trust_remote_code=False,
    )


def _encoder() -> Any:
    """Serialize first loading so concurrent sessions do not duplicate model memory."""
    with _model_lock:
        return _load_encoder()


def chunk_article(text: str) -> list[str]:
    """Bound the index and overlap adjacent passages to preserve context."""
    return [text[start:start + 1200] for start in range(0, len(text), 1050)][:80]


@lru_cache(maxsize=16)
def _index(_destination: str, text: str) -> tuple[list[str], np.ndarray]:
    chunks = chunk_article(text)
    vectors = np.asarray(
        _encoder().encode(chunks, normalize_embeddings=True, batch_size=16), dtype=np.float32,
    )
    return chunks, vectors


def semantic_passages(destination: str, text: str, query: str) -> list[dict[str, Any]]:
    """Search a destination-scoped semantic vector index by cosine similarity."""
    chunks, vectors = _index(destination, text)
    query_vector = np.asarray(
        _encoder().encode([query], normalize_embeddings=True), dtype=np.float32,
    )[0]
    scores = vectors @ query_vector
    order = np.argsort(-scores, kind="stable")[:3]
    source = f"https://en.wikivoyage.org/wiki/{quote(destination.replace(' ', '_'), safe='')}"
    return [
        {"text": chunks[int(index)][:950], "score": round(float(scores[index]), 4), "url": source}
        for index in order
    ]

# Public function to retrieve destination context from Wikivoyage
def get_destination_context(destination: str, query: str = "") -> dict[str, Any]:
    """Return semantically relevant passages or an explicit optional failure."""
    if not isinstance(destination, str):
        raise ValueError("Destination must be text.")
    normalized_destination = destination.strip()
    if not normalized_destination:
        raise ValueError("Destination is required.")
    try:
        available, context = _cached_context(normalized_destination)
        if not available:
            return {"available": False, "context": "", "passages": [], "reason": "No guide found."}
        passages = semantic_passages(normalized_destination, context, query or destination)
    except (requests.RequestException, ValueError, OSError, ImportError, RuntimeError) as error:
        logger.warning("Wikivoyage retrieval failed (%s).", type(error).__name__)
        return {
            "available": False, "context": "", "passages": [],
            "reason": "Optional semantic guide retrieval is unavailable. Check the model setup and network.",
        }
    return {
        "available": True, "context": "\n\n".join(item["text"] for item in passages),
        "passages": passages,
    }
