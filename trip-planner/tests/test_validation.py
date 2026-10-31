import json

import pytest

from utils.output_parser import parse_itinerary
from utils.schemas import Itinerary
from utils.validation import validate_itinerary, validate_trip_request

VALID_ITINERARY = {
    "destination": "Seattle",
    "overview": "Three days of food, museums, and parks.",
    "travel_notes": "Check opening hours before visiting.",
    "daily_plan": [
        {"day": day, "title": f"Day {day}", "activities": ["Visit a local museum"]}
        for day in range(1, 4)
    ],
}


def test_valid_request():
    assert validate_trip_request("Seattle", 3) == []


@pytest.mark.parametrize(
    ("destination", "duration"),
    [("", 3), ("Seattle", 0), ("Seattle", 31)],
)
def test_invalid_trip_request(destination, duration):
    assert validate_trip_request(destination, duration)


def test_parse_itinerary_recovers_markdown_fenced_json():
    parsed = parse_itinerary(f"```json\n{json.dumps(VALID_ITINERARY)}\n```")

    assert isinstance(parsed, Itinerary)
    assert len(parsed.daily_plan) == 3


def test_parse_itinerary_rejects_malformed_output():
    with pytest.raises(ValueError, match="not valid itinerary JSON"):
        parse_itinerary("not json")


def test_itinerary_validation_checks_destination_and_day_count():
    itinerary = Itinerary.model_validate(VALID_ITINERARY)

    assert validate_itinerary(itinerary, "Seattle, WA", 3) is itinerary
    with pytest.raises(ValueError, match="destination"):
        validate_itinerary(itinerary, "Portland", 3)
    with pytest.raises(ValueError, match="each requested day"):
        validate_itinerary(itinerary, "Seattle", 2)


def test_itinerary_validation_normalizes_destination_diacritics():
    itinerary_data = {**VALID_ITINERARY, "destination": "São Paulo"}
    itinerary = Itinerary.model_validate(itinerary_data)

    assert validate_itinerary(itinerary, "Sao Paulo", 3) is itinerary
