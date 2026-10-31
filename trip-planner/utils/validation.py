"""Input and itinerary validation."""

from __future__ import annotations

import re
import unicodedata

from utils.schemas import Itinerary


def validate_trip_request(
    destination: str,
    duration: int,
    interests: str = "",
    budget: str = "",
    travel_style: str = "",
    additional_request: str = "",
    refinement: str = "",
) -> list[str]:
    """Return user-correctable request errors."""
    errors = []
    if not isinstance(destination, str) or not destination.strip():
        errors.append("Destination is required.")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 30:
        errors.append("Trip duration must be between 1 and 30 days.")
    for label, value, limit in (
        ("Destination", destination, 200),
        ("Interests", interests, 500),
        ("Budget", budget, 200),
        ("Travel style", travel_style, 200),
        ("Additional request", additional_request, 1000),
        ("Refinement", refinement, 1000),
    ):
        if not isinstance(value, str):
            errors.append(f"{label} must be text.")
        elif len(value) > limit:
            errors.append(f"{label} must be {limit} characters or fewer.")
    return errors


def validate_itinerary(
    itinerary: Itinerary,
    destination: str,
    duration: int,
) -> Itinerary:
    """Enforce destination consistency and one itinerary day per requested day."""
    def normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        unaccented = "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
        return re.sub(r"[^a-z0-9]", "", unaccented)

    expected = normalize(destination)
    actual = normalize(itinerary.destination)
    if not expected or (expected not in actual and actual not in expected):
        raise ValueError("The generated itinerary destination did not match the request.")

    days = [item.day for item in itinerary.daily_plan]
    if days != list(range(1, duration + 1)):
        raise ValueError("The generated itinerary did not include each requested day.")
    return itinerary
