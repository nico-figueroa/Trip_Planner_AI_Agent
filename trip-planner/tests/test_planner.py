import pytest

from utils.agent import TripPlannerAgent
from utils.openai_agent import PlanningError
from utils.schemas import Itinerary


def valid_itinerary():
    return Itinerary.model_validate(
        {
            "destination": "Seattle",
            "overview": "Three days in Seattle.",
            "travel_notes": "Check transit schedules.",
            "daily_plan": [
                {"day": day, "title": f"Day {day}", "activities": ["Visit a museum"]}
                for day in range(1, 4)
            ],
        }
    )


class FakeAgent:
    def __init__(self, trace):
        self.trace = trace

    def run(self, request):
        return valid_itinerary(), self.trace


def test_trip_planner_returns_coordinates_and_tool_results():
    trace = [
        {
            "tool": "geocode_city",
            "success": True,
            "result": {
                "latitude": 47.6,
                "longitude": -122.3,
                "city": "Seattle",
                "country": "United States",
            },
        },
        {
            "tool": "find_nearby_pois",
            "success": True,
            "result": [{"name": "Seattle Art Museum"}],
        },
    ]

    result = TripPlannerAgent(agent=FakeAgent(trace)).generate_trip_plan(
        "Seattle",
        3,
        interests="Museums",
    )

    assert result["location"]["latitude"] == 47.6
    assert result["pois"][0]["name"] == "Seattle Art Museum"
    assert len(result["itinerary"]["daily_plan"]) == 3


def test_trip_planner_requires_verified_destination():
    planner = TripPlannerAgent(agent=FakeAgent([]))

    with pytest.raises(PlanningError, match="could not be verified"):
        planner.generate_trip_plan("Seattle", 3)


def test_trip_planner_rejects_long_prompts_before_model_call():
    planner = TripPlannerAgent(agent=FakeAgent([]))

    with pytest.raises(ValueError, match="Additional request"):
        planner.generate_trip_plan("Seattle", 3, additional_request="x" * 1001)
