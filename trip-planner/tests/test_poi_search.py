import pytest
import requests

from utils import poi_search
from utils.poi_search import find_nearby_pois


class MockResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "elements": [
                {
                    "type": "node",
                    "lat": 47.6,
                    "lon": -122.3,
                    "tags": {"name": "City Museum", "tourism": "museum"},
                },
                {
                    "type": "way",
                    "center": {"lat": 47.61, "lon": -122.31},
                    "tags": {"name": "Central Park", "leisure": "park"},
                },
                {
                    "type": "node",
                    "lat": 47.6,
                    "lon": -122.3,
                    "tags": {"tourism": "attraction"},
                },
            ]
        }


def test_find_nearby_pois_maps_supported_elements(monkeypatch):
    calls = []

    def mock_post(url, *, data, headers, timeout):
        calls.append((url, data, headers, timeout))
        return MockResponse()

    monkeypatch.setattr(poi_search.requests, "post", mock_post)
    poi_search._cached_pois.cache_clear()

    pois = find_nearby_pois(47.6, -122.3)

    assert [poi["name"] for poi in pois] == ["City Museum", "Central Park"]
    assert pois[0]["category"] == "Museum"
    assert pois[1]["latitude"] == 47.61
    assert calls[0][2]["User-Agent"] == poi_search.USER_AGENT
    assert "restaurant" in calls[0][1]["data"]


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (0, 181)],
)
def test_find_nearby_pois_rejects_invalid_coordinates(latitude, longitude):
    with pytest.raises(ValueError):
        find_nearby_pois(latitude, longitude)


def test_overpass_failure_uses_geoapify_with_equivalent_output(monkeypatch):
    calls = []

    def fail_overpass(*args):
        raise requests.ReadTimeout("not available")

    def geoapify_response(latitude, longitude, radius, api_key):
        calls.append((latitude, longitude, radius, api_key))
        return {
            "features": [
                {
                    "properties": {
                        "name": "City Museum",
                        "lat": 47.6,
                        "lon": -122.3,
                        "categories": ["entertainment", "entertainment.museum"],
                    }
                },
                {"properties": {"name": "Bad point", "lat": 999, "lon": 0}},
            ]
        }

    monkeypatch.setattr(poi_search, "_cached_pois", fail_overpass)
    monkeypatch.setattr(poi_search, "resolve_secret", lambda name: ("test-key", ".env"))
    monkeypatch.setattr(poi_search, "_request_geoapify", geoapify_response)
    poi_search._cached_geoapify_pois.cache_clear()

    result = find_nearby_pois(47.6, -122.3)

    assert result == [
        {
            "name": "City Museum",
            "category": "Museum",
            "latitude": 47.6,
            "longitude": -122.3,
            "source": "Geoapify",
        }
    ]
    assert len(calls) == 1
    result[0]["name"] = "Changed by caller"
    assert find_nearby_pois(47.6, -122.3)[0]["name"] == "City Museum"
    assert len(calls) == 1


def test_overpass_failure_without_fallback_key_remains_visible(monkeypatch):
    def fail_overpass(*args):
        raise requests.ReadTimeout("not available")

    monkeypatch.setattr(poi_search, "_cached_pois", fail_overpass)
    monkeypatch.setattr(poi_search, "resolve_secret", lambda name: (None, None))

    with pytest.raises(requests.ReadTimeout):
        find_nearby_pois(47.6, -122.3)


def test_empty_overpass_result_does_not_consume_fallback_quota(monkeypatch):
    monkeypatch.setattr(poi_search, "_cached_pois", lambda *args: ())

    def unexpected_secret_lookup(name):
        pytest.fail("Empty Overpass results must not call Geoapify.")

    monkeypatch.setattr(poi_search, "resolve_secret", unexpected_secret_lookup)

    assert find_nearby_pois(47.6, -122.3) == []


def test_geoapify_key_is_sent_in_header_not_url(monkeypatch):
    def post(url, *, headers, json, timeout):
        assert url == poi_search.GEOAPIFY_URL
        assert headers["x-api-key"] == "test-key"
        assert "test-key" not in url
        assert json["filter"]["type"] == "circle"
        assert json["limit"] == 20
        return MockResponse()

    monkeypatch.setattr(poi_search.requests, "post", post)
    monkeypatch.setattr(poi_search, "_respect_rate_limit", lambda: None)

    poi_search._request_geoapify(47.6, -122.3, 3000, "test-key")


def test_both_provider_failures_are_reported_without_raw_errors(monkeypatch):
    def fail_provider(*args):
        raise requests.ReadTimeout("private provider body")

    monkeypatch.setattr(poi_search, "_cached_pois", fail_provider)
    monkeypatch.setattr(poi_search, "_cached_geoapify_pois", fail_provider)
    monkeypatch.setattr(poi_search, "resolve_secret", lambda name: ("test-key", ".env"))

    with pytest.raises(ValueError, match="both Overpass and Geoapify") as error:
        find_nearby_pois(47.6, -122.3)
    assert "private provider body" not in str(error.value)
