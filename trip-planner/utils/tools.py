"""OpenAI function definitions and deterministic tool dispatch."""

from __future__ import annotations

from typing import Any, Callable

from utils.geocoding import geocode_city
from utils.poi_search import find_nearby_pois
from utils.rag import get_destination_context

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "geocode_city",
        "description": "Resolve a destination to its city, country, and geographic coordinates.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "find_nearby_pois",
        "description": (
            "Retrieve nearby named museums, parks, attractions, restaurants, cafes, "
            "and landmarks from OpenStreetMap. Use coordinates returned by geocode_city."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
            },
            "required": ["latitude", "longitude"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_destination_context",
        "description": (
            "Optionally retrieve concise Wikivoyage destination context. "
            "An unavailable result is non-fatal."
        ),
        "parameters": {
            "type": "object",
            "properties": {"destination": {"type": "string"}},
            "required": ["destination"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "geocode_city": geocode_city,
    "find_nearby_pois": find_nearby_pois,
    "get_destination_context": get_destination_context,
}


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Execute a registered tool after validating its invocation shape."""
    function = TOOL_REGISTRY.get(tool_name)
    if function is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    return function(**arguments)
