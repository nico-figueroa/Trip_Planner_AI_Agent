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


def test_trip_planner_merges_regional_bases_and_places():
    def geocode(city, latitude, longitude):
        return {
            "tool": "geocode_city",
            "success": True,
            "result": {"latitude": latitude, "longitude": longitude, "city": city},
        }

    def places(*names):
        return {
            "tool": "find_nearby_pois",
            "success": True,
            "result": [
                {"name": name, "latitude": 47.6, "longitude": -122.3} for name in names
            ],
        }

    trace = [
        geocode("Seattle", 47.6, -122.3),
        geocode("Tacoma", 47.25, -122.44),
        geocode("Seattle", 47.6, -122.3),
        places("Museum", "Park"),
        places("Park", "Waterfront"),
    ]

    result = TripPlannerAgent(agent=FakeAgent(trace)).generate_trip_plan("Seattle", 3)

    assert result["stops"] == [{"name": "Tacoma", "latitude": 47.25, "longitude": -122.44}]
    assert [poi["name"] for poi in result["pois"]] == ["Museum", "Park", "Waterfront"]


def test_trip_planner_requires_verified_destination():
    planner = TripPlannerAgent(agent=FakeAgent([]))

    with pytest.raises(PlanningError, match="could not be verified"):
        planner.generate_trip_plan("Seattle", 3)


def test_trip_planner_rejects_long_prompts_before_model_call():
    planner = TripPlannerAgent(agent=FakeAgent([]))

    with pytest.raises(ValueError, match="Additional request"):
        planner.generate_trip_plan("Seattle", 3, additional_request="x" * 1001)


SEATTLE_TRACE = [
    {
        "tool": "geocode_city",
        "success": True,
        "result": {"latitude": 47.6, "longitude": -122.3, "city": "Seattle"},
    }
]


class ScriptedAgent:
    def __init__(self, *itineraries):
        self.itineraries = list(itineraries)
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self.itineraries.pop(0), list(SEATTLE_TRACE)


def commitment_check(result):
    return next(
        entry["result"]
        for entry in result["trace"]
        if entry["tool"] == "verify_fixed_commitments"
    )


def itinerary_with_day_two(activity):
    plan = valid_itinerary()
    plan.daily_plan[1].activities = [activity]
    return plan


def test_misplaced_fixed_commitment_triggers_one_model_repair():
    from datetime import date

    agent = ScriptedAgent(
        valid_itinerary(),
        itinerary_with_day_two("Christmas dinner with family in Escazu"),
    )

    result = TripPlannerAgent(agent=agent).generate_trip_plan(
        "Seattle",
        3,
        additional_request="Dec 24 Escazu christmas dinner",
        start_date=date(2026, 12, 23),
    )

    assert len(agent.requests) == 2
    assert "Day 2: Dec 24 Escazu christmas dinner" in agent.requests[1]
    assert result["itinerary"]["daily_plan"][1]["activities"] == [
        "Christmas dinner with family in Escazu"
    ]
    assert commitment_check(result)["repaired_by_model"] is True


def test_ignored_fixed_commitment_is_rejected_after_one_repair():
    from datetime import date

    agent = ScriptedAgent(valid_itinerary(), valid_itinerary())

    with pytest.raises(PlanningError, match="still violates"):
        TripPlannerAgent(agent=agent).generate_trip_plan(
            "Seattle", 3, additional_request="Dec 24 Escazu christmas dinner",
            start_date=date(2026, 12, 23),
        )
    assert len(agent.requests) == 2


def test_single_day_regeneration_preserves_every_other_field():
    import json

    original = valid_itinerary().model_dump()
    changed = valid_itinerary()
    changed.daily_plan[0].activities = ["Unexpected change"]
    changed.daily_plan[1].activities = ["New day two"]
    changed.overview = "Unexpected overview"
    scripted = ScriptedAgent(changed)
    result = TripPlannerAgent(agent=scripted).generate_trip_plan(
        "Seattle", 3, existing_itinerary=original, refinement="Change day two", target_day=2,
    )
    payload = json.loads(scripted.requests[0])
    assert payload["target_day"] == 2
    assert "Copy every other day" in payload["instruction"]
    actual = result["itinerary"]
    assert actual["daily_plan"][0] == original["daily_plan"][0]
    assert actual["daily_plan"][2] == original["daily_plan"][2]
    assert actual["overview"] == original["overview"]
    assert actual["travel_notes"] == original["travel_notes"]
    assert actual["daily_plan"][1]["activities"] == ["New day two"]
