"""High-level trip planning and itinerary validation."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from utils.openai_agent import OpenAITripAgent, PlanningError
from utils.openai_client import get_client
from utils.prompts import build_itinerary_prompt, commitment_is_scheduled, fixed_commitments
from utils.schemas import Itinerary
from utils.validation import validate_itinerary, validate_trip_request

logger = logging.getLogger(__name__)
MAX_PLAN_POIS = 80


class TripPlannerAgent:
    """Collect agent output and enforce the product's final itinerary contract."""

    def __init__(
        self,
        agent: OpenAITripAgent | None = None,
    ):
        self.agent = agent

    def generate_trip_plan(
        self,
        destination: str,
        duration: int,
        interests: str = "",
        budget: str = "",
        travel_style: str = "",
        additional_request: str = "",
        existing_itinerary: dict[str, Any] | None = None,
        start_date: date | None = None,
        refinement: str = "",
    ) -> dict[str, Any]:
        """Generate a grounded plan with coordinates, POIs, and execution trace.

        ``additional_request`` holds the original trip constraints and is kept on
        refinement; ``refinement`` holds only the requested change.
        """
        errors = validate_trip_request(
            destination,
            duration,
            interests,
            budget,
            travel_style,
            additional_request,
            refinement,
        )
        if start_date is not None and not isinstance(start_date, date):
            errors.append("Start date must be a calendar date.")
        if errors:
            logger.warning("Trip request validation failed.")
            raise ValueError(" ".join(errors))

        request_fields = {
            "destination": destination,
            "duration": duration,
            "interests": interests,
            "budget": budget,
            "travel_style": travel_style,
            "additional_request": additional_request,
            "start_date": start_date,
        }
        request = build_itinerary_prompt(
            **request_fields,
            existing_itinerary=existing_itinerary,
            refinement=refinement,
        )
        agent = self.agent or OpenAITripAgent(client=get_client())
        itinerary, trace = agent.run(request)
        try:
            itinerary = validate_itinerary(itinerary, destination, duration)
        except ValueError:
            logger.warning("Generated itinerary failed product validation.")
            raise

        pinned = fixed_commitments(additional_request, start_date, duration)
        missing = _unscheduled_commitments(itinerary, pinned)
        repaired = False
        if missing:
            logger.warning(
                "%d fixed commitment(s) were not on their required day; requesting one repair.",
                len(missing),
            )
            repair_request = build_itinerary_prompt(
                **request_fields,
                existing_itinerary=itinerary.model_dump(),
                refinement="Move these fixed commitments onto exactly these days and "
                "re-plan the surrounding travel: "
                + "; ".join(f"Day {item['day']}: {item['commitment']}" for item in missing),
            )
            try:
                repaired_itinerary, repair_trace = agent.run(repair_request)
                itinerary = validate_itinerary(repaired_itinerary, destination, duration)
                trace.extend(repair_trace)
                repaired = True
            except (PlanningError, ValueError) as error:
                logger.warning("Commitment repair failed (%s).", type(error).__name__)
            missing = _unscheduled_commitments(itinerary, pinned)
        for item in missing:
            # Last resort: the constraint must be visible on its day even if the model ignored it.
            day = next((day for day in itinerary.daily_plan if day.day == item["day"]), None)
            if day is not None:
                day.activities.insert(0, f"Fixed commitment: {item['commitment']}")
        if pinned:
            trace.append(
                {
                    "tool": "verify_fixed_commitments",
                    "success": True,
                    "result": {
                        "commitments": len(pinned),
                        "repaired_by_model": repaired,
                        "inserted_by_planner": [item["day"] for item in missing],
                    },
                }
            )

        geocode_entry = next(
            (
                entry
                for entry in trace
                if entry["tool"] == "geocode_city" and entry["success"]
            ),
            None,
        )
        if geocode_entry is None:
            geocode_error = next(
                (entry for entry in trace if entry["tool"] == "geocode_city"),
                None,
            )
            if (
                geocode_error
                and geocode_error.get("error_type") == "DestinationNotFoundError"
            ):
                raise PlanningError(
                    f"Couldn't find {destination}. Check the destination and try again."
                )
            raise PlanningError(
                "The destination could not be verified. Please try again."
            )

        location = geocode_entry["result"]
        if (
            not -90 <= location["latitude"] <= 90
            or not -180 <= location["longitude"] <= 180
        ):
            raise PlanningError("The destination lookup returned invalid coordinates.")
        trace.append(
            {
                "tool": "validate_itinerary",
                "success": True,
                "result": {
                    "destination_match": True,
                    "requested_days": duration,
                    "validated_days": len(itinerary.daily_plan),
                    "coordinates_available": True,
                },
            }
        )
        logger.info("Generated itinerary passed final validation.")

        context_entry = next(
            (
                entry
                for entry in trace
                if entry["tool"] == "get_destination_context" and entry["success"]
            ),
            None,
        )

        return {
            "destination": itinerary.destination,
            "duration": duration,
            "interests": interests,
            "budget": budget,
            "travel_style": travel_style,
            "additional_request": additional_request,
            "start_date": start_date.isoformat() if start_date else None,
            "location": location,
            "stops": _collect_stops(trace, location),
            "pois": _collect_pois(trace),
            "travel_context": (
                context_entry["result"].get("context", "") if context_entry else ""
            ),
            "itinerary": itinerary.model_dump(),
            "trace": trace,
        }


def _unscheduled_commitments(
    itinerary: Itinerary,
    pinned: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return fixed commitments whose required day does not mention them."""
    days = {
        day.day: " ".join([day.title, *day.activities]) for day in itinerary.daily_plan
    }
    return [
        item
        for item in pinned
        if not commitment_is_scheduled(item["commitment"], days.get(item["day"], ""))
    ]


def _successful_results(trace: list[dict[str, Any]], tool_name: str) -> list[Any]:
    return [
        entry["result"]
        for entry in trace
        if entry.get("tool") == tool_name and entry.get("success")
    ]


def _collect_stops(
    trace: list[dict[str, Any]],
    location: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return additional geocoded regional bases, excluding the main destination."""
    seen = {(round(location["latitude"], 3), round(location["longitude"], 3))}
    stops: list[dict[str, Any]] = []
    for result in _successful_results(trace, "geocode_city"):
        if not isinstance(result, dict):
            continue
        try:
            latitude = float(result["latitude"])
            longitude = float(result["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        key = (round(latitude, 3), round(longitude, 3))
        if key in seen or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            continue
        seen.add(key)
        stops.append(
            {
                "name": result.get("city") or result.get("display_name") or "Stop",
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return stops


def _collect_pois(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge places from every successful POI search, removing duplicates."""
    seen: set[tuple[str, Any, Any]] = set()
    pois: list[dict[str, Any]] = []
    for result in _successful_results(trace, "find_nearby_pois"):
        if not isinstance(result, list):
            continue
        for poi in result:
            if not isinstance(poi, dict):
                continue
            key = (str(poi.get("name", "")), poi.get("latitude"), poi.get("longitude"))
            if key in seen:
                continue
            seen.add(key)
            pois.append(poi)
            if len(pois) == MAX_PLAN_POIS:
                return pois
    return pois
