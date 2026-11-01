"""OpenAI Responses API function-calling loop."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, cast

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
MAX_TOOL_ROUNDS = 6 # Maximum number of tool execution rounds allowed
MAX_TOOL_CALLS = 16 # Maximum number of individual tool calls allowed
SKIPPED_TOOL_MESSAGE = ( 
    "Tool budget reached. Build the final itinerary from the data already gathered."
) # Message displayed when the tool execution budget is exhausted
def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """OpenAI strict mode requires every object property, including nullable ones."""
    result = json.loads(json.dumps(schema))

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["required"] = list(node.get("properties", {}))
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(result)
    return result


RESPONSE_FORMAT = {
    "format": {
        "type": "json_schema",
        "name": "trip_itinerary",
        "schema": _strict_schema(Itinerary.model_json_schema()),
        "strict": True,
    }
} # Response format for the model


class PlanningError(RuntimeError):
    """A user-safe error raised when the planner cannot complete a request."""


def _tool_error_message(tool_name: str, error: Exception) -> str:
    if tool_name == "geocode_city" and isinstance(error, DestinationNotFoundError):
        return "No matching destination was found."
    if tool_name == "geocode_city":
        return "Destination lookup is temporarily unavailable."
    if tool_name in ("find_nearby_pois", "search_pois"):
        return "Nearby place search is temporarily unavailable."
    if tool_name == "get_destination_context":
        return "Optional travel guide context is unavailable."
    return "The requested tool could not be completed."


def _model_payload(tool_name: str, result: Any) -> Any:
    """Drop display-only fields so tool outputs stay small in the model context."""
    if tool_name in ("find_nearby_pois", "search_pois") and isinstance(result, list):
        return [
            {key: value for key, value in item.items() if key not in ("address", "url", "id")}
            if isinstance(item, dict)
            else item
            for item in result
        ]
    return result


class OpenAITripAgent:
    """Run a bounded Responses API tool loop and validate the final itinerary."""

    def __init__(
        self, client: Any | None = None, model: str = OPENAI_MODEL,
        boosts: dict[str, float] | None = None,
    ):
        self.client = client if client is not None else get_client()
        self.model = model
        self.boosts = boosts or {}

    def _create_response(
        self, tool_choice: Literal["auto", "none"], **request: Any
    ) -> Any:
        return self.client.responses.create(
            model=self.model,
            tools=cast(Any, TOOL_DEFINITIONS),
            tool_choice=tool_choice,
            text=cast(Any, RESPONSE_FORMAT),
            **request,
        )

    def _execute_call(self, call: Any, trace: list[dict[str, Any]]) -> Any:
        arguments: dict[str, Any] = {}
        try:
            arguments = json.loads(call.arguments)
            if call.name in ("search_pois", "find_nearby_pois"):
                result = execute_tool("search_pois", {**arguments, "boosts": self.boosts})
            else:
                result = execute_tool(call.name, arguments)
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
            logger.warning("Agent tool failed: %s (%s).", call.name, type(error).__name__)
            return {"error": message}

        trace.append(
            {"tool": call.name, "arguments": arguments, "success": True, "result": result}
        )
        logger.info("Agent tool completed: %s.", call.name)
        return _model_payload(call.name, result)

    def run(
        self,
        trip_request: str,
    ) -> tuple[Itinerary, list[dict[str, Any]]]:
        """Return a validated itinerary and user-visible tool execution trace.

        When the round or call budget is reached, remaining calls are skipped and
        the model is asked to finish with the data it already has.
        """
        trace: list[dict[str, Any]] = []
        executed_calls = 0
        tool_choice: Literal["auto", "none"] = "auto"
        try:
            response = self._create_response(
                tool_choice,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": trip_request},
                ],
            )

            for round_number in range(1, MAX_TOOL_ROUNDS + 2):
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
                    logger.info(
                        "Agent returned a structured itinerary after %d tool calls.",
                        executed_calls,
                    )
                    return itinerary, trace
                if tool_choice == "none":
                    break

                tool_outputs = []
                for call in tool_calls:
                    if executed_calls < MAX_TOOL_CALLS:
                        executed_calls += 1
                        output = self._execute_call(call, trace)
                    else:
                        output = {"error": SKIPPED_TOOL_MESSAGE}
                    tool_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(output, ensure_ascii=False),
                        }
                    )

                if round_number >= MAX_TOOL_ROUNDS or executed_calls >= MAX_TOOL_CALLS:
                    tool_choice = "none"
                    logger.info(
                        "Tool budget reached after %d calls; requesting the final itinerary.",
                        executed_calls,
                    )
                response = self._create_response(
                    tool_choice,
                    previous_response_id=response.id,
                    input=tool_outputs,
                )
        except APIError as error:
            raise PlanningError(describe_openai_error(error)) from error

        logger.warning("Agent kept requesting tools after the final itinerary request.")
        raise PlanningError("The planner could not complete its tool workflow.")
