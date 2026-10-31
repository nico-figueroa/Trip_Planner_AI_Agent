import json
from datetime import date

from utils.prompts import build_itinerary_prompt


def test_prompt_maps_start_date_to_each_trip_day():
    payload = json.loads(
        build_itinerary_prompt(
            "Costa Rica",
            19,
            "Beaches",
            additional_request="Dec 24: dinner in Escazu",
            start_date=date(2026, 12, 21),
        )
    )

    assert len(payload["day_dates"]) == 19
    assert payload["day_dates"][3] == "Day 4: Thu 2026-12-24 (Christmas Eve)"
    assert payload["day_dates"][11] == "Day 12: Fri 2027-01-01 (New Year's Day)"


def test_dated_commitments_are_pinned_to_trip_days():
    payload = json.loads(
        build_itinerary_prompt(
            "Costa Rica",
            19,
            "Beaches",
            additional_request=(
                "Trip between Dec 21 2026 and Jan 8 2027. Fixed commitments: "
                "Dec 22 birthday party in San Jose; 24 December dinner in Escazu; "
                "2026-12-31 family party in Escazu\nJanuary 1st family lunch; "
                "Feb 3 is outside the trip"
            ),
            start_date=date(2026, 12, 21),
        )
    )

    assert [(item["day"], item["date"]) for item in payload["fixed_commitments"]] == [
        (2, "Tue 2026-12-22"),
        (4, "Thu 2026-12-24"),
        (11, "Thu 2026-12-31"),
        (12, "Fri 2027-01-01"),
    ]
    assert payload["fixed_commitments"][1]["commitment"] == "24 December dinner in Escazu"


def test_refinement_keeps_original_constraints():
    payload = json.loads(
        build_itinerary_prompt(
            "Costa Rica",
            2,
            "Beaches",
            additional_request="Dec 22: birthday party in San Jose",
            existing_itinerary={"destination": "Costa Rica"},
            refinement="Add a beach day",
        )
    )

    assert payload["additional_request"] == "Dec 22: birthday party in San Jose"
    assert payload["refinement"] == "Add a beach day"
    assert "day_dates" not in payload
    assert "fixed_commitments" not in payload


def test_comma_separated_commitments_and_holidays_are_pinned():
    payload = json.loads(
        build_itinerary_prompt(
            "Costa Rica",
            19,
            "Volcano, beach",
            additional_request=(
                "Fixed commitments: December 22 San Jose birthday party, December 24 "
                "San Jose christmas dinner, December 25 Palmares christmas party, "
                "December 31 new years eve party Escazu, January 1 lunch San Jose, "
                "January 7 packing Escazu."
            ),
            start_date=date(2026, 12, 21),
        )
    )

    assert [(item["day"], item["commitment"]) for item in payload["fixed_commitments"]] == [
        (2, "December 22 San Jose birthday party"),
        (4, "December 24 San Jose christmas dinner"),
        (5, "December 25 Palmares christmas party"),
        (11, "December 31 new years eve party Escazu"),
        (12, "January 1 lunch San Jose"),
        (18, "January 7 packing Escazu"),
    ]
    assert payload["day_dates"][3] == "Day 4: Thu 2026-12-24 (Christmas Eve)"
    assert payload["day_dates"][4] == "Day 5: Fri 2026-12-25 (Christmas Day)"
    assert payload["free_windows"] == [
        "Day 1 (1 free day): stay within about 1.5 hours of the Day 2 commitment towns",
        "Day 3 (1 free day): stay within about 1.5 hours of the Day 2 and Day 4 "
        "commitment towns",
        "Days 6-10 (5 free days): long trips allowed if travel days are included",
        "Days 13-17 (5 free days): long trips allowed if travel days are included",
        "Day 19 (1 free day): stay within about 1.5 hours of the Day 18 commitment towns",
    ]


def test_commitment_scheduling_check_ignores_accents_and_dates():
    from utils.prompts import commitment_is_scheduled

    assert commitment_is_scheduled(
        "December 24 San Jose christmas dinner", "Christmas Eve dinner in San José"
    )
    assert not commitment_is_scheduled(
        "December 24 San Jose christmas dinner", "Arenal Volcano hike"
    )
