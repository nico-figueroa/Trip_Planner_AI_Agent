"""Overpass POI retrieval with an optional Geoapify fallback."""

from __future__ import annotations

import copy
import logging
import math
import threading
import time
from functools import lru_cache
from typing import Any

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from utils.config import GEOAPIFY_URL, OVERPASS_URL, USER_AGENT, resolve_secret

logger = logging.getLogger(__name__)
MAX_POIS = 20
GEOAPIFY_CATEGORIES = {
    "entertainment.museum": "Museum",
    "leisure.park": "Park",
    "tourism.sights": "Landmark",
    "catering.restaurant": "Restaurant",
    "catering.cafe": "Cafe",
}
_request_lock = threading.Lock()
_last_request_at = 0.0


def _is_retryable(error: BaseException) -> bool:
    if not isinstance(error, requests.RequestException):
        return False
    response = getattr(error, "response", None)
    return response is None or response.status_code == 429 or response.status_code >= 500


def _respect_rate_limit() -> None:
    global _last_request_at
    with _request_lock:
        delay = 1.0 - (time.monotonic() - _last_request_at)
        if delay > 0:
            time.sleep(delay)
        _last_request_at = time.monotonic()


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


def _category(tags: dict[str, Any]) -> str:
    for key in ("tourism", "amenity", "leisure", "historic"):
        if tags.get(key):
            return str(tags[key]).replace("_", " ").title()
    return "Point of interest"


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=1, max=2),
    stop=stop_after_attempt(2),
    reraise=True,
)
def _request_overpass(query: str) -> dict[str, Any]:
    _respect_rate_limit()
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": USER_AGENT},
        timeout=(5, 20),
    )
    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=64)
def _cached_pois(latitude: float, longitude: float, radius: int) -> tuple[dict[str, Any], ...]:
    query = f"""
    [out:json][timeout:15];
    (
      nwr(around:{radius},{latitude},{longitude})["tourism"~"^(attraction|museum|gallery|theme_park|zoo|aquarium)$"];
      nwr(around:{radius},{latitude},{longitude})["amenity"~"^(restaurant|cafe)$"];
      nwr(around:{radius},{latitude},{longitude})["leisure"~"^(park|garden)$"];
      nwr(around:{radius},{latitude},{longitude})["historic"];
    );
    out center {MAX_POIS};
    """
    data = _request_overpass(query)
    if not isinstance(data, dict):
        raise ValueError("Overpass returned an invalid response.")
    elements = data.get("elements", [])
    if not isinstance(elements, list):
        raise ValueError("Overpass returned an invalid element list.")
    pois: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()

    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags", {})
        if not isinstance(tags, dict):
            continue
        name = tags.get("name")
        center = element.get("center", {})
        if not isinstance(center, dict):
            center = {}
        poi_latitude = element.get("lat", center.get("lat"))
        poi_longitude = element.get("lon", center.get("lon"))
        if not name or poi_latitude is None or poi_longitude is None:
            continue

        try:
            point = (str(name), float(poi_latitude), float(poi_longitude))
        except (TypeError, ValueError):
            continue
        if not -90 <= point[1] <= 90 or not -180 <= point[2] <= 180:
            continue
        if point in seen:
            continue
        seen.add(point)
        pois.append(
            {
                "name": point[0],
                "category": _category(tags),
                "latitude": point[1],
                "longitude": point[2],
                "source": "Overpass",
            }
        )
        if len(pois) == MAX_POIS:
            break

    return tuple(pois)


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=1, max=2),
    stop=stop_after_attempt(2),
    reraise=True,
)
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


@lru_cache(maxsize=64)
def _cached_geoapify_pois(
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
        categories = properties.get("categories", [])
        if not isinstance(categories, list):
            categories = []
        category = next(
            (
                label
                for key, label in GEOAPIFY_CATEGORIES.items()
                if any(
                    isinstance(value, str)
                    and (value == key or value.startswith(f"{key}."))
                    for value in categories
                )
            ),
            "Attraction",
        )
        pois.append(
            {
                "name": point[0],
                "category": category,
                "latitude": point[1],
                "longitude": point[2],
                "source": "Geoapify",
            }
        )
        if len(pois) == MAX_POIS:
            break
    return tuple(pois)


def find_nearby_pois(
    latitude: float,
    longitude: float,
    radius: int = 3000,
) -> list[dict[str, Any]]:
    """Use Overpass first; fall back on provider failure when Geoapify is configured."""
    latitude, longitude = _validate_search(latitude, longitude, radius)
    try:
        pois = _cached_pois(latitude, longitude, radius)
    except (requests.RequestException, ValueError) as error:
        logger.warning("Overpass request failed (%s).", type(error).__name__)
        api_key, _ = resolve_secret("GEOAPIFY_API_KEY")
        if not api_key:
            raise
        logger.info("Using the configured Geoapify fallback for nearby places.")
        try:
            pois = _cached_geoapify_pois(latitude, longitude, radius, api_key)
        except (requests.RequestException, ValueError) as fallback_error:
            logger.warning(
                "Geoapify fallback failed (%s).", type(fallback_error).__name__
            )
            raise ValueError(
                "Nearby place search is unavailable from both Overpass and Geoapify."
            ) from fallback_error
    return copy.deepcopy(list(pois))
