import pytest
import requests

from utils import poi_search
from utils.poi_search import find_nearby_pois

GEOAPIFY_RESPONSE = {
    "features": [
        {
            "properties": {
                "name": "City Museum",
                "lat": 47.6,
                "lon": -122.3,
                "categories": ["entertainment", "entertainment.museum"],
                "address_line1": "City Museum",
                "address_line2": "100 Main Street, Seattle, WA 98101",
            }
        },
        {
            "properties": {
                "name": "Central Park",
                "lat": 47.61,
                "lon": -122.31,
                "categories": ["leisure.park"],
                "address_line1": "200 Park Avenue",
                "address_line2": "Seattle, WA 98101",
            }
        },
        {"properties": {"name": "Bad point", "lat": 999, "lon": 0}},
        {"properties": {"lat": 47.6, "lon": -122.3}},
    ]
}


@pytest.fixture(autouse=True)
def configured_key(monkeypatch):
    monkeypatch.setattr(poi_search, "resolve_secret", lambda name: ("test-key", ".env"))
    poi_search._cached_pois.cache_clear()


def test_find_nearby_pois_maps_geoapify_places_with_addresses(monkeypatch):
    calls = []

    def geoapify_response(latitude, longitude, radius, api_key):
        calls.append((latitude, longitude, radius, api_key))
        return GEOAPIFY_RESPONSE

    monkeypatch.setattr(poi_search, "_request_geoapify", geoapify_response)

    result = find_nearby_pois(47.6, -122.3)

    assert result == [
        {
            "name": "City Museum",
            "category": "Museum",
            "address": "100 Main Street, Seattle, WA 98101",
            "latitude": 47.6,
            "longitude": -122.3,
        },
        {
            "name": "Central Park",
            "category": "Park",
            "address": "200 Park Avenue, Seattle, WA 98101",
            "latitude": 47.61,
            "longitude": -122.31,
        },
    ]
    result[0]["name"] = "Changed by caller"
    assert find_nearby_pois(47.6, -122.3)[0]["name"] == "City Museum"
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (0, 181)],
)
def test_find_nearby_pois_rejects_invalid_coordinates(latitude, longitude):
    with pytest.raises(ValueError):
        find_nearby_pois(latitude, longitude)


def test_missing_geoapify_key_is_reported(monkeypatch):
    monkeypatch.setattr(poi_search, "resolve_secret", lambda name: (None, None))

    with pytest.raises(ValueError, match="GEOAPIFY_API_KEY"):
        find_nearby_pois(47.6, -122.3)


def test_geoapify_key_is_sent_in_header_not_url(monkeypatch):
    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return GEOAPIFY_RESPONSE

    def post(url, *, headers, json, timeout):
        assert url == poi_search.GEOAPIFY_URL
        assert headers["x-api-key"] == "test-key"
        assert headers["User-Agent"] == poi_search.USER_AGENT
        assert "test-key" not in url
        assert json["filter"]["type"] == "circle"
        assert json["limit"] == 20
        return MockResponse()

    monkeypatch.setattr(poi_search.requests, "post", post)
    monkeypatch.setattr(poi_search, "_respect_rate_limit", lambda: None)

    assert poi_search._request_geoapify(47.6, -122.3, 3000, "test-key") == GEOAPIFY_RESPONSE


def test_provider_failure_is_reported_without_raw_errors(monkeypatch):
    def fail_provider(*args):
        raise requests.ReadTimeout("private provider body")

    monkeypatch.setattr(poi_search, "_cached_pois", fail_provider)

    with pytest.raises(ValueError, match="temporarily unavailable") as error:
        find_nearby_pois(47.6, -122.3)
    assert "private provider body" not in str(error.value)
