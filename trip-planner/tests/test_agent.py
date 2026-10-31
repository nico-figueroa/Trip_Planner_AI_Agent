import json
from types import SimpleNamespace

import pytest
import httpx
from openai import AuthenticationError

from utils import openai_agent
from utils.openai_agent import OpenAITripAgent

ITINERARY = {
    "destination": "Seattle",
    "overview": "A three-day trip.",
    "travel_notes": "Check transit schedules.",
    "daily_plan": [
        {"day": day, "title": f"Day {day}", "activities": ["Visit a museum"]}
        for day in range(1, 4)
    ],
}


class FakeResponses:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.responses)


def function_call(name, call_id, arguments):
    return SimpleNamespace(
        type="function_call",
        name=name,
        call_id=call_id,
        arguments=json.dumps(arguments),
    )


def response(response_id, output, output_text=""):
    return SimpleNamespace(id=response_id, output=output, output_text=output_text)


def test_agent_executes_tool_calls_and_returns_structured_itinerary(monkeypatch):
    responses = FakeResponses(
        [
            response("r1", [function_call("geocode_city", "c1", {"city": "Seattle"})]),
            response(
                "r2",
                [
                    function_call(
                        "find_nearby_pois",
                        "c2",
                        {"latitude": 47.6, "longitude": -122.3},
                    )
                ],
            ),
            response("r3", [], json.dumps(ITINERARY)),
        ]
    )
    tool_results = {
        "geocode_city": {
            "latitude": 47.6,
            "longitude": -122.3,
            "city": "Seattle",
            "country": "United States",
            "display_name": "Seattle",
        },
        "find_nearby_pois": [{"name": "Seattle Art Museum"}],
    }
    monkeypatch.setattr(
        openai_agent,
        "execute_tool",
        lambda name, arguments: tool_results[name],
    )
    agent = OpenAITripAgent(client=SimpleNamespace(responses=responses))

    itinerary, trace = agent.run("Plan three days in Seattle.")

    assert itinerary.destination == "Seattle"
    assert [entry["tool"] for entry in trace] == ["geocode_city", "find_nearby_pois"]
    assert responses.requests[1]["previous_response_id"] == "r1"
    assert responses.requests[1]["input"][0]["call_id"] == "c1"
    assert responses.requests[2]["input"][0]["call_id"] == "c2"
    assert responses.requests[0]["tools"]
    assert responses.requests[0]["text"]["format"]["strict"] is True


def test_agent_reports_tool_errors_to_model(monkeypatch):
    responses = FakeResponses(
        [
            response("r1", [function_call("geocode_city", "c1", {"city": "Nowhere"})]),
            response("r2", [], json.dumps(ITINERARY)),
        ]
    )

    def fail_tool(name, arguments):
        raise ValueError("not found")

    monkeypatch.setattr(openai_agent, "execute_tool", fail_tool)
    agent = OpenAITripAgent(client=SimpleNamespace(responses=responses))

    _, trace = agent.run("Plan three days in Seattle.")

    assert trace[0]["success"] is False
    assert json.loads(responses.requests[1]["input"][0]["output"])["error"]


def test_agent_forces_final_itinerary_when_tool_budget_is_reached(monkeypatch):
    many_calls = [
        function_call("geocode_city", f"c{index}", {"city": f"Town {index}"})
        for index in range(openai_agent.MAX_TOOL_CALLS + 2)
    ]
    responses = FakeResponses(
        [response("r1", many_calls), response("r2", [], json.dumps(ITINERARY))]
    )
    executed = []
    monkeypatch.setattr(
        openai_agent,
        "execute_tool",
        lambda name, arguments: executed.append(arguments) or {"latitude": 1.0},
    )
    agent = OpenAITripAgent(client=SimpleNamespace(responses=responses))

    itinerary, trace = agent.run("Plan nineteen days in Costa Rica.")

    assert itinerary.destination == "Seattle"
    assert len(executed) == len(trace) == openai_agent.MAX_TOOL_CALLS
    final_request = responses.requests[1]
    assert final_request["tool_choice"] == "none"
    assert len(final_request["input"]) == len(many_calls)
    assert json.loads(final_request["input"][-1]["output"]) == {
        "error": openai_agent.SKIPPED_TOOL_MESSAGE
    }


def test_agent_forces_final_itinerary_after_max_rounds(monkeypatch):
    rounds = [
        response(f"r{index}", [function_call("geocode_city", f"c{index}", {"city": "X"})])
        for index in range(openai_agent.MAX_TOOL_ROUNDS)
    ]
    responses = FakeResponses([*rounds, response("final", [], json.dumps(ITINERARY))])
    monkeypatch.setattr(openai_agent, "execute_tool", lambda name, arguments: {})
    agent = OpenAITripAgent(client=SimpleNamespace(responses=responses))

    agent.run("Plan three days in Seattle.")

    assert [request["tool_choice"] for request in responses.requests] == [
        *["auto"] * openai_agent.MAX_TOOL_ROUNDS,
        "none",
    ]


def test_poi_addresses_are_not_sent_back_to_model(monkeypatch):
    responses = FakeResponses(
        [
            response(
                "r1",
                [function_call("find_nearby_pois", "c1", {"latitude": 1, "longitude": 2})],
            ),
            response("r2", [], json.dumps(ITINERARY)),
        ]
    )
    poi = {"name": "Museum", "address": "1 Main Street", "latitude": 1, "longitude": 2}
    monkeypatch.setattr(openai_agent, "execute_tool", lambda name, arguments: [poi])
    agent = OpenAITripAgent(client=SimpleNamespace(responses=responses))

    _, trace = agent.run("Plan three days in Seattle.")

    assert trace[0]["result"][0]["address"] == "1 Main Street"
    assert "address" not in json.loads(responses.requests[1]["input"][0]["output"])[0]


def test_agent_rejects_malformed_final_itinerary():
    responses = FakeResponses([response("r1", [], "not json")])
    agent = OpenAITripAgent(client=SimpleNamespace(responses=responses))

    with pytest.raises(ValueError, match="not valid itinerary JSON"):
        agent.run("Plan three days in Seattle.")


def test_agent_authentication_failure_is_actionable():
    class FailingResponses:
        def create(self, **kwargs):
            raise AuthenticationError(
                "raw provider authentication body",
                response=httpx.Response(
                    401,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body=None,
            )

    agent = OpenAITripAgent(client=SimpleNamespace(responses=FailingResponses()))

    with pytest.raises(openai_agent.PlanningError, match="HTTP 401") as error:
        agent.run("Plan three days in Seattle.")
    assert "raw provider" not in str(error.value)
