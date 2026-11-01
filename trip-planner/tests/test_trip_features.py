from datetime import date
from decimal import Decimal

import pytest

from utils.trips.trip_features import budget_totals, map_data, money, resolve_duration, safe_url


def test_inclusive_range_overrides_duration_across_year_boundary():
    assert resolve_duration(3, date(2026, 12, 21), date(2027, 1, 8)) == (19, True)


@pytest.mark.parametrize("start,end", [
    (None, date(2026, 1, 1)),
    (date(2026, 1, 2), date(2026, 1, 1)),
    (date(2026, 1, 1), date(2026, 2, 1)),
])
def test_invalid_ranges_are_rejected(start, end):
    with pytest.raises(ValueError):
        resolve_duration(3, start, end)


def test_budget_uses_decimal_and_separates_estimates_from_actual_spending():
    plan = {
        "budget_total": "1.00", "expenses": [{"amount": "0.10"}, {"amount": "0.20"}],
        "itinerary": {"daily_plan": [{"estimated_cost": 10.1}, {"estimated_cost": 2.2}]},
    }
    assert budget_totals(plan) == (Decimal("0.30"), Decimal("0.70"), Decimal("12.30"))
    plan["itinerary"]["daily_plan"][0]["estimated_cost"] = None
    assert budget_totals(plan)[2] is None


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1"])
def test_invalid_expenses_are_rejected(amount):
    with pytest.raises(ValueError):
        money(amount)


def test_urls_never_allow_script_or_credential_links():
    assert safe_url("javascript:alert(1)") == ""
    assert safe_url("https://user:password@example.com/") == ""
    assert safe_url(None, 9, -84).startswith("https://www.openstreetmap.org/")


def test_path_uses_temporal_order_across_days_and_filters_without_mutation():
    plan = {
        "pois": [
            {"name": "Museum", "latitude": 10, "longitude": 20},
            {"name": "Beach", "latitude": 11, "longitude": 21},
        ],
        "itinerary": {"daily_plan": [
            {"day": 1, "locations": ["Beach"], "activities": ["Beach"]},
            {"day": 2, "locations": ["Museum"], "activities": ["Museum"]},
        ]},
    }
    points, paths = map_data(plan)
    assert paths == [[[21, 11], [20, 10]]]
    filtered, _ = map_data(plan, 2)
    assert [point["name"] for point in filtered] == ["Museum"]
    assert len(plan["itinerary"]["daily_plan"]) == 2
    assert len(points) == 2


def test_unresolved_location_breaks_path_instead_of_fabricating_geometry():
    plan = {
        "pois": [
            {"name": "A", "latitude": 1, "longitude": 1},
            {"name": "B", "latitude": 2, "longitude": 2},
        ],
        "itinerary": {"daily_plan": [{"day": 1, "locations": ["A", "Unknown", "B"]}]},
    }
    assert map_data(plan)[1] == []


def test_plan_import_strips_account_metadata_and_validates_itinerary():
    import json
    from utils.trips.trip_features import import_plan_json

    data = {
        "owner": "not-an-authentication-claim", "destination": "Seattle", "duration": 1,
        "location": {"latitude": 47, "longitude": -122},
        "itinerary": {
            "destination": "Seattle", "overview": "Overview", "travel_notes": "Notes",
            "daily_plan": [{"day": 1, "title": "Arrival", "activities": ["Rest"]}],
        },
    }
    result = import_plan_json(json.dumps(data).encode())
    assert "owner" not in result
    data["pois"] = ["invalid point"]
    with pytest.raises(ValueError):
        import_plan_json(json.dumps(data).encode())
