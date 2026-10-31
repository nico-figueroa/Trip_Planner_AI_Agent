"""Optional, bounded Wikivoyage destination retrieval."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from utils.config import USER_AGENT, WIKIVOYAGE_API_URL

logger = logging.getLogger(__name__)
MAX_CONTEXT_CHARS = 3000


def _is_retryable(error: BaseException) -> bool:
    if not isinstance(error, requests.RequestException):
        return False
    response = getattr(error, "response", None)
    return response is None or response.status_code == 429 or response.status_code >= 500


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(2),
    reraise=True,
)
def _request_wikivoyage(destination: str) -> dict[str, Any]:
    response = requests.get(
        WIKIVOYAGE_API_URL,
        params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "exchars": MAX_CONTEXT_CHARS,
            "titles": destination,
            "format": "json",
            "redirects": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=(5, 15),
    )
    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=64)
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
    extract = str(page.get("extract", "")).strip()[:MAX_CONTEXT_CHARS]
    return bool(extract), extract


def get_destination_context(destination: str) -> dict[str, bool | str]:
    """Retrieve a short Wikivoyage extract, returning an empty context on failure."""
    if not isinstance(destination, str):
        raise ValueError("Destination must be text.")
    normalized_destination = destination.strip()
    if not normalized_destination:
        raise ValueError("Destination is required.")
    try:
        available, context = _cached_context(normalized_destination)
    except (requests.RequestException, ValueError) as error:
        logger.warning("Wikivoyage retrieval failed (%s).", type(error).__name__)
        return {"available": False, "context": ""}
    return {"available": available, "context": context}
