"""Geoapify Places POI retrieval."""

from __future__ import annotations

import copy
import logging
import math
import threading
import time
from functools import lru_cache
from typing import Any

import requests # HTTP requests library for making API calls
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from utils.config import GEOAPIFY_URL, USER_AGENT, resolve_secret
from utils.trip_features import poi_key, safe_url

logger = logging.getLogger(__name__)
MAX_POIS = 20 # Maximum number of POIs to retrieve per request
GEOAPIFY_CATEGORIES = { # Mapping of Geoapify category keys to human-readable labels
    "entertainment.museum": "Museum",
    "national_park": "National park",
    "leisure.park": "Park",
    "tourism.sights": "Landmark",
    "tourism.attraction": "Attraction",
    "catering.restaurant": "Restaurant",
    "catering.cafe": "Cafe",
    "beach": "Beach",
}
_request_lock = threading.Lock() # Lock to synchronize access to the last request timestamp
_last_request_at = 0.0 # Timestamp of the last Geoapify request to enforce rate limiting

# Helper functions for Geoapify POI search

# Determine if an error is retryable for Geoapify requests
def _is_retryable(error: BaseException) -> bool:
    if not isinstance(error, requests.RequestException):
        return False
    response = getattr(error, "response", None)
    return response is None or response.status_code == 429 or response.status_code >= 500

# Respect the rate limit for Geoapify requests
def _respect_rate_limit() -> None:
    global _last_request_at
    with _request_lock:
        delay = 1.0 - (time.monotonic() - _last_request_at)
        if delay > 0:
            time.sleep(delay)
        _last_request_at = time.monotonic()


# Validate the search parameters for Geoapify POI search
# Ensures latitude, longitude, and radius are within acceptable ranges
def _validate_search(latitude: float, longitude: float, radius: int) -> tuple[float, float]:
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as error:
        raise ValueError("Coordinates must be numbers.") from error
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")
    if not 100 <= radius <= 10000:
        raise ValueError("Search radius must be between 100 and 10000 meters.")
    return latitude, longitude

# Determine the primary category label for a Geoapify POI based on its categories
def _category(categories: Any) -> str:
    if not isinstance(categories, list):
        return "Attraction"
    return next(
        (
            label
            for key, label in GEOAPIFY_CATEGORIES.items()
            if any(
                isinstance(value, str) and (value == key or value.startswith(f"{key}."))
                for value in categories
            )
        ),
        "Attraction",
    )

# Extract the address for a Geoapify POI, excluding the place name
def _address(properties: dict[str, Any], name: str) -> str:
    """Return the street/locality part of a Geoapify address without the place name."""
    line1 = str(properties.get("address_line1") or "").strip()
    line2 = str(properties.get("address_line2") or "").strip()
    if line1 and line1 != name:
        return ", ".join(part for part in (line1, line2) if part)
    return line2 or str(properties.get("formatted") or "").strip()

# Retry decorator for Geoapify requests
@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=1, max=2),
    stop=stop_after_attempt(2),
    reraise=True,
)

# Make a request to the Geoapify POI search API with retry logic
def _request_geoapify(
    latitude: float,
    longitude: float,
    radius: int,
    api_key: str,
) -> dict[str, Any]:
    _respect_rate_limit()
    response = requests.post(
        GEOAPIFY_URL,
        headers={"User-Agent": USER_AGENT, "x-api-key": api_key},
        json={
            "categories": list(GEOAPIFY_CATEGORIES),
            "filter": {
                "type": "circle",
                "lat": latitude,
                "lon": longitude,
                "radius": radius,
            },
            "bias": {"type": "proximity", "lat": latitude, "lon": longitude},
            "limit": MAX_POIS,
        },
        timeout=(5, 15),
    )
    response.raise_for_status()
    return response.json()

# Cached wrapper around Geoapify POI search to reduce API calls
@lru_cache(maxsize=64) # max 64 cached results because of memory constraints
def _cached_pois(
    latitude: float,
    longitude: float,
    radius: int,
    api_key: str,
) -> tuple[dict[str, Any], ...]:
    data = _request_geoapify(latitude, longitude, radius, api_key)
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise ValueError("Geoapify returned an invalid response.")
    pois: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()
    for feature in data["features"]:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict) or not properties.get("name"):
            continue
        try:
            point = (
                str(properties["name"]),
                float(properties["lat"]),
                float(properties["lon"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if not -90 <= point[1] <= 90 or not -180 <= point[2] <= 180 or point in seen:
            continue
        seen.add(point)
        pois.append(
            {
                "name": point[0],
                "category": _category(properties.get("categories")),
                "address": _address(properties, point[0]),
                "latitude": point[1],
                "longitude": point[2],
                "id": str(properties.get("place_id") or ""),
                "url": safe_url(properties.get("website"), point[1], point[2]),
            }
        )
        if len(pois) == MAX_POIS:
            break
    return tuple(pois)

# Public function to find nearby POIs using the cached Geoapify search
def find_nearby_pois(
    latitude: float,
    longitude: float,
    radius: int = 3000,
) -> list[dict[str, Any]]:
    """Return named places near a coordinate from the Geoapify Places API."""
    latitude, longitude = _validate_search(latitude, longitude, radius)
    api_key, _ = resolve_secret("GEOAPIFY_API_KEY")
    if not api_key:
        logger.warning("Nearby place search skipped: GEOAPIFY_API_KEY is not configured.")
        raise ValueError("Nearby place search requires GEOAPIFY_API_KEY.")
    try:
        pois = _cached_pois(latitude, longitude, radius, api_key)
    except requests.RequestException as error:
        logger.warning("Geoapify request failed (%s).", type(error).__name__)
        raise ValueError("Nearby place search is temporarily unavailable.") from error
    return copy.deepcopy(list(pois))


def search_pois(
    latitude: float, longitude: float, radius: int = 3000,
    boosts: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Apply current feedback outside the raw retrieval cache, preserving stable ties."""
    pois = find_nearby_pois(latitude, longitude, radius)
    for rank, poi in enumerate(pois):
        poi["id"] = poi_key(poi)
        poi["boost"] = float((boosts or {}).get(poi["id"], 0))
        poi["score"] = 1 - rank / max(len(pois), 1) + poi["boost"]
    return sorted(pois, key=lambda poi: -poi["score"])
