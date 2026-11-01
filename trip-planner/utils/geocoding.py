"""Nominatim geocoding with rate limiting and bounded memoization."""

from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache
from typing import Any

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from utils.config import NOMINATIM_URL, USER_AGENT

logger = logging.getLogger(__name__)
_request_lock = threading.Lock() # Lock to synchronize access to the last request timestamp
_last_request_at = 0.0 # Timestamp of the last Nominatim request to enforce rate limiting


class DestinationNotFoundError(ValueError):
    """Raised when Nominatim cannot resolve a destination."""


def _is_retryable(error: BaseException) -> bool:
    if not isinstance(error, requests.RequestException):
        return False
    response = getattr(error, "response", None)
    return response is None or response.status_code == 429 or response.status_code >= 500


def _respect_rate_limit() -> None:
    global _last_request_at
    with _request_lock:
        delay = 1.1 - (time.monotonic() - _last_request_at)
        if delay > 0:
            time.sleep(delay)
        _last_request_at = time.monotonic()


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)

# Internal function to perform a Nominatim request with retry and rate limiting
def _request_nominatim(city: str) -> list[dict[str, Any]]:
    _respect_rate_limit()
    response = requests.get(
        NOMINATIM_URL,
        params={"q": city, "format": "jsonv2", "addressdetails": 1, "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=(5, 15),
    )
    response.raise_for_status()
    return response.json()

# Internal function to perform a cached geocode lookup using Nominatim
@lru_cache(maxsize=256) # Cache up to 256 geocoding results to reduce repeated Nominatim requests
def _cached_geocode(city: str) -> tuple[float, float, str, str, str] | None:
    results = _request_nominatim(city)
    if not results:
        return None
    if not isinstance(results, list) or not isinstance(results[0], dict):
        raise ValueError("Nominatim returned an invalid response.")

    result = results[0]
    address = result.get("address", {})
    if not isinstance(address, dict):
        address = {}
    resolved_city = next(
        (
            address[key]
            for key in ("city", "town", "village", "municipality", "hamlet")
            if address.get(key)
        ),
        city,
    )
    try:
        latitude = float(result["lat"])
        longitude = float(result["lon"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Nominatim returned invalid coordinates.") from error
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Nominatim returned coordinates outside valid bounds.")

    return (
        latitude,
        longitude,
        str(address.get("country", "")),
        str(resolved_city),
        str(result.get("display_name", resolved_city)),
    )

# Public function to geocode a city using the cached Nominatim lookup
def geocode_city(city: str) -> dict[str, float | str]:
    """Resolve a city or destination to coordinates and address details."""
    if not isinstance(city, str):
        raise ValueError("Destination must be text.")
    normalized_city = city.strip()
    if not normalized_city:
        raise ValueError("Destination is required.")

    try:
        result = _cached_geocode(normalized_city)
    except requests.RequestException as error:
        logger.warning("Nominatim request failed (%s).", type(error).__name__)
        raise

    if result is None:
        raise DestinationNotFoundError(
            f"No location was found for {normalized_city}."
        )

    latitude, longitude, country, resolved_city, display_name = result
    return {
        "latitude": latitude,
        "longitude": longitude,
        "country": country,
        "city": resolved_city,
        "display_name": display_name,
    }
