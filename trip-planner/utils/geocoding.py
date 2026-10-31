import requests

from utils.config import (
    NOMINATIM_URL,
    USER_AGENT
)


def geocode_city(city: str):

    headers = {
        "User-Agent": USER_AGENT
    }

    params = {
        "q": city,
        "format": "json",
        "limit": 1
    }

    response = requests.get(
        NOMINATIM_URL,
        params=params,
        headers=headers,
        timeout=10
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        return None

    return {
        "latitude": float(results[0]["lat"]),
        "longitude": float(results[0]["lon"]),
        "display_name": results[0]["display_name"]
    }
