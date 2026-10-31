"""High-level trip planning and itinerary validation."""

from __future__ import annotations

import logging
from typing import Any

from utils.openai_agent import OpenAITripAgent, PlanningError
from utils.openai_client import get_client
from utils.prompts import build_itinerary_prompt
from utils.validation import validate_itinerary, validate_trip_request

logger = logging.getLogger(__name__)


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
    ) -> dict[str, Any]:
        """Generate a grounded plan with coordinates, POIs, and execution trace."""
        errors = validate_trip_request(
            destination,
            duration,
            interests,
            budget,
            travel_style,
            additional_request,
        )
        if errors:
            logger.warning("Trip request validation failed.")
            raise ValueError(" ".join(errors))

        request = build_itinerary_prompt(
            destination=destination,
            duration=duration,
            interests=interests,
            budget=budget,
            travel_style=travel_style,
            additional_request=additional_request,
            existing_itinerary=existing_itinerary,
        )
        agent = self.agent or OpenAITripAgent(client=get_client())
        itinerary, trace = agent.run(request)
        try:
            itinerary = validate_itinerary(itinerary, destination, duration)
        except ValueError:
            logger.warning("Generated itinerary failed product validation.")
            raise

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

        poi_entry = next(
            (
                entry
                for entry in trace
                if entry["tool"] == "find_nearby_pois" and entry["success"]
            ),
            None,
        )
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
            "location": location,
            "pois": poi_entry["result"] if poi_entry else [],
            "travel_context": (
                context_entry["result"].get("context", "") if context_entry else ""
            ),
            "itinerary": itinerary.model_dump(),
            "trace": trace,
        }
