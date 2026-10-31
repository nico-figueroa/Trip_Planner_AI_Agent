"""OpenAI Responses API function-calling loop."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from openai import APIError

from utils.config import OPENAI_MODEL
from utils.geocoding import DestinationNotFoundError
from utils.openai_client import describe_openai_error, get_client
from utils.output_parser import parse_itinerary
from utils.prompts import SYSTEM_PROMPT
from utils.schemas import Itinerary
from utils.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 5


class PlanningError(RuntimeError):
    """A user-safe error raised when the planner cannot complete a request."""


def _tool_error_message(tool_name: str, error: Exception) -> str:
    if tool_name == "geocode_city" and isinstance(error, DestinationNotFoundError):
        return "No matching destination was found."
    if tool_name == "geocode_city":
        return "Destination lookup is temporarily unavailable."
    if tool_name == "find_nearby_pois":
        return "Nearby place search is temporarily unavailable."
    if tool_name == "get_destination_context":
        return "Optional travel guide context is unavailable."
    return "The requested tool could not be completed."


class OpenAITripAgent:
    """Run a bounded Responses API tool loop and validate the final itinerary."""

    def __init__(self, client: Any | None = None, model: str = OPENAI_MODEL):
        self.client = client if client is not None else get_client()
        self.model = model

    def run(
        self,
        trip_request: str,
    ) -> tuple[Itinerary, list[dict[str, Any]]]:
        """Return a validated itinerary and user-visible tool execution trace."""
        trace: list[dict[str, Any]] = []
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": trip_request},
                ],
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "trip_itinerary",
                        "schema": Itinerary.model_json_schema(),
                        "strict": True,
                    }
                },
            )

            for _ in range(MAX_TOOL_ROUNDS + 1):
                tool_calls = [
                    item
                    for item in response.output
                    if getattr(item, "type", None) == "function_call"
                ]
                if not tool_calls:
                    try:
                        itinerary = parse_itinerary(response.output_text or "")
                    except ValueError:
                        logger.warning("Structured itinerary output failed validation.")
                        raise
                    logger.info("Agent returned a structured itinerary.")
                    return itinerary, trace

                if len(trace) + len(tool_calls) > MAX_TOOL_ROUNDS * 3:
                    raise PlanningError("The planner exceeded its tool execution limit.")

                tool_outputs = []
                for call in tool_calls:
                    arguments: dict[str, Any] = {}
                    try:
                        arguments = json.loads(call.arguments)
                        result = execute_tool(call.name, arguments)
                        trace.append(
                            {
                                "tool": call.name,
                                "arguments": arguments,
                                "success": True,
                                "result": result,
                            }
                        )
                        logger.info("Agent tool completed: %s.", call.name)
                    except (
                        DestinationNotFoundError,
                        requests.RequestException,
                        TypeError,
                        ValueError,
                    ) as error:
                        message = _tool_error_message(call.name, error)
                        trace.append(
                            {
                                "tool": call.name,
                                "arguments": arguments,
                                "success": False,
                                "error": message,
                                "error_type": type(error).__name__,
                            }
                        )
                        logger.warning(
                            "Agent tool failed: %s (%s).",
                            call.name,
                            type(error).__name__,
                        )
                        result = {"error": message}

                    tool_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(result, ensure_ascii=False),
                        }
                    )

                response = self.client.responses.create(
                    model=self.model,
                    previous_response_id=response.id,
                    input=tool_outputs,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "trip_itinerary",
                            "schema": Itinerary.model_json_schema(),
                            "strict": True,
                        }
                    },
                )
        except APIError as error:
            raise PlanningError(describe_openai_error(error)) from error

        raise PlanningError("The planner could not complete its tool workflow.")
