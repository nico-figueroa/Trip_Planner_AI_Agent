"""Deterministic dates, expense arithmetic, and temporal map data."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse


def resolve_duration(duration: int, start: date | None, end: date | None) -> tuple[int, bool]:
    """Inclusive date ranges take precedence; reject invalid or oversized requests."""
    if end is not None and start is None:
        raise ValueError("Select a start date before selecting an end date.")
    result = duration
    if start is not None and end is not None:
        result = (end - start).days + 1
    if isinstance(result, bool) or not isinstance(result, int) or not 1 <= result <= 30:
        raise ValueError("Choose a trip of 1 to 30 days with end date on or after start date.")
    return result, result != duration


def safe_url(value: Any, latitude: float | None = None, longitude: float | None = None) -> str:
    """Allow ordinary web links only; use an honest OSM location link as fallback."""
    if isinstance(value, str):
        try:
            parsed = urlparse(value)
            if parsed.scheme in ("https", "http") and parsed.hostname and not parsed.username and not parsed.password:
                return value
        except ValueError:
            return ""
    if latitude is not None and longitude is not None:
        return f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=16/{latitude}/{longitude}"
    return ""


def poi_key(poi: dict[str, Any]) -> str:
    """Stable location identity for feedback across repeated requests."""
    if poi.get("id"):
        return str(poi["id"])
    value = f"{normalize(str(poi.get('name', '')))}|{float(poi['latitude']):.5f}|{float(poi['longitude']):.5f}"
    return hashlib.sha256(value.encode()).hexdigest()


def normalize(text: str) -> str:
    """Accent-insensitive matching of retrieved location names."""
    value = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in value if not unicodedata.combining(char)).strip()


def money(value: Any) -> Decimal:
    """Validate non-negative finite amounts without floating-point arithmetic."""
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Amount must be a valid number.") from error
    if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
        raise ValueError("Amount must be finite and between 0 and 1,000,000,000.")
    return amount.quantize(Decimal("0.01"))


def budget_totals(plan: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal | None]:
    spent = sum((money(row["amount"]) for row in plan.get("expenses", [])), Decimal("0"))
    total = money(plan.get("budget_total", 0))
    estimates = [day.get("estimated_cost") for day in plan["itinerary"].get("daily_plan", [])]
    estimated = (
        sum((money(amount) for amount in estimates), Decimal("0"))
        if estimates and all(amount is not None for amount in estimates) else None
    )
    return spent, total - spent, estimated


def selected_days(plan: dict[str, Any], day: int | None) -> list[dict[str, Any]]:
    return [
        item for item in plan.get("itinerary", {}).get("daily_plan", [])
        if day is None or item.get("day") == day
    ]


def map_data(plan: dict[str, Any], day: int | None = None) -> tuple[list[dict[str, Any]], list[list[list[float]]]]:
    """Use only verified coordinates and preserve each day's visit sequence.

    Unresolved visits break the path, so lines never imply a fabricated stop or
    route across missing geometry. Paths are schematic, not driving directions.
    """
    candidates: list[dict[str, Any]] = []
    center = plan.get("location", {})
    if center:
        candidates.append({**center, "name": center.get("city") or plan.get("destination"), "category": "Destination"})
    candidates.extend({**stop, "category": "Regional base"} for stop in plan.get("stops", []))
    candidates.extend(plan.get("pois", []))
    candidates.extend({**stop, "category": "Itinerary stop"} for stop in plan.get("resolved_locations", []))
    points: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            lat, lon = float(candidate["latitude"]), float(candidate["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        points.append({**candidate, "latitude": lat, "longitude": lon})
    paths: list[list[list[float]]] = []
    visited: set[tuple[float, float]] = set()
    segment: list[list[float]] = []
    for item in selected_days(plan, day):
        names = item.get("locations", [])
        if not names:
            text = normalize(" ".join(item.get("activities", [])))
            names = [
                point["name"] for point in sorted(
                    points, key=lambda point: text.find(normalize(str(point["name"]))),
                )
                if normalize(str(point["name"])) and normalize(str(point["name"])) in text
            ]
        if not names:
            if len(segment) > 1:
                paths.append(segment)
            segment = []
        for name in names:
            key = normalize(name)
            point = next((p for p in points if normalize(str(p["name"])) == key), None)
            if point is None:
                if len(segment) > 1:
                    paths.append(segment)
                segment = []
                continue
            coordinate = [point["longitude"], point["latitude"]]
            visited.add((point["latitude"], point["longitude"]))
            if not segment or segment[-1] != coordinate:
                segment.append(coordinate)
    if len(segment) > 1:
        paths.append(segment)
    unique: dict[tuple[float, float], dict[str, Any]] = {}
    for point in points:
        coordinate = (point["latitude"], point["longitude"])
        if day is not None and coordinate not in visited:
            continue
        stop = coordinate in visited
        unique[coordinate] = {
            **point, "radius": 120 if stop else 80,
            "color": [244, 166, 35] if stop else [38, 133, 153],
        }
    return list(unique.values()), paths


def preserve_other_days(
    generated: dict[str, Any], original: dict[str, Any], target_day: int,
) -> dict[str, Any]:
    """Single-day regeneration cannot mutate any other itinerary field."""
    replacement = next(day for day in generated["daily_plan"] if day["day"] == target_day)
    result = copy.deepcopy(original)
    result["daily_plan"] = [
        copy.deepcopy(replacement) if day["day"] == target_day else day
        for day in result["daily_plan"]
    ]
    return result


def import_plan_json(content: bytes) -> dict[str, Any]:
    """Import a single plan (or a legacy active plan), never shared account state."""
    from utils.planning.schemas import Itinerary
    from utils.planning.validation import validate_itinerary

    if len(content) > 500000:
        raise ValueError("Plan JSON must be no larger than 500 KB.")
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError("The upload is not valid plan JSON.") from error
    if isinstance(payload, dict) and "active_itinerary" in payload:
        payload = payload["active_itinerary"]
    if not isinstance(payload, dict):
        raise ValueError("Upload a plan object with an itinerary.")
    itinerary = Itinerary.model_validate(payload.get("itinerary"))
    duration = payload.get("duration", len(itinerary.daily_plan))
    destination = payload.get("destination", itinerary.destination)
    validate_itinerary(itinerary, destination, duration)
    allowed = (
        "destination", "duration", "interests", "budget", "travel_style", "additional_request",
        "start_date", "currency", "budget_total", "expenses", "location", "pois", "stops",
        "resolved_locations", "unresolved_locations",
    )
    plan = {key: copy.deepcopy(payload[key]) for key in allowed if key in payload}
    plan.update(destination=destination, duration=duration, itinerary=itinerary.model_dump(), trace=[])
    if plan.get("start_date"):
        date.fromisoformat(plan["start_date"])
    if plan.get("currency", "USD") not in ("USD", "EUR", "GBP", "CRC", "CAD", "AUD"):
        raise ValueError("Unsupported plan currency.")
    for field in ("pois", "stops", "resolved_locations", "expenses"):
        if not isinstance(plan.get(field, []), list) or len(plan.get(field, [])) > 200:
            raise ValueError("Invalid or oversized plan list.")
    for field in ("location", "pois", "stops", "resolved_locations"):
        normalized = []
        points = [plan[field]] if field == "location" and field in plan else plan.get(field, [])
        for point in points:
            if not isinstance(point, dict):
                raise ValueError("Location records must be objects.")
            latitude, longitude = float(point["latitude"]), float(point["longitude"])
            if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("Invalid imported coordinates.")
            entry: dict[str, Any] = {
                key: str(point[key])[:500] for key in ("name", "category", "address", "id", "city")
                if key in point
            }
            entry.update(latitude=latitude, longitude=longitude, url=safe_url(point.get("url"), latitude, longitude))
            normalized.append(entry)
        if field == "location":
            if normalized:
                plan[field] = normalized[0]
        else:
            plan[field] = normalized
    for row in plan.get("expenses", []):
        if (
            not isinstance(row, dict) or row.get("category") not in ("Transport", "Lodging", "Food", "Activities", "Other")
            or not isinstance(row.get("description"), str) or len(row["description"]) > 200
            or isinstance(row.get("day"), bool) or not isinstance(row.get("day"), int)
            or not 1 <= row["day"] <= duration
        ):
            raise ValueError("Invalid expense record.")
    if not isinstance(plan.get("unresolved_locations", []), list) or any(
        not isinstance(name, str) for name in plan.get("unresolved_locations", [])
    ):
        raise ValueError("Invalid unresolved location names.")
    budget_totals(plan)
    return plan
