"""Parsing and validation for model-generated itinerary JSON."""

from __future__ import annotations

import json

from pydantic import ValidationError # Exception raised for Pydantic model validation errors

from utils.schemas import Itinerary

# Public function to parse and validate the itinerary JSON returned by the AI planner
def parse_itinerary(response_text: str) -> Itinerary:
    """Parse strict JSON, recovering a JSON object wrapped in surrounding text."""
    if not response_text or not response_text.strip():
        raise ValueError("The planner returned an empty itinerary.")

    content = response_text.strip()
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```")
        content = content.removesuffix("```").strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        if start < 0:
            raise ValueError("The planner response was not valid itinerary JSON.")
        try:
            data, _ = json.JSONDecoder().raw_decode(content[start:])
        except json.JSONDecodeError as error:
            raise ValueError("The planner response was not valid itinerary JSON.") from error

    try:
        return Itinerary.model_validate(data)
    except ValidationError as error:
        issues = ", ".join(
            ".".join(str(part) for part in item["loc"])
            for item in error.errors()[:4]
        )
        raise ValueError(f"The planner returned an invalid itinerary ({issues}).") from error
