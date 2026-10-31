import pytest

from utils import geocoding
from utils.geocoding import DestinationNotFoundError, geocode_city


class MockResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


def test_geocode_city_returns_coordinates_and_address(monkeypatch):
    calls = []

    def mock_get(url, *, params, headers, timeout):
        calls.append((url, params, headers, timeout))
        return MockResponse(
            [
                {
                    "lat": "47.6062",
                    "lon": "-122.3321",
                    "display_name": "Seattle, Washington, United States",
                    "address": {"city": "Seattle", "country": "United States"},
                }
            ]
        )

    monkeypatch.setattr(geocoding.requests, "get", mock_get)
    monkeypatch.setattr(geocoding, "_respect_rate_limit", lambda: None)
    geocoding._cached_geocode.cache_clear()

    result = geocode_city("Seattle")

    assert result["latitude"] == 47.6062
    assert result["longitude"] == -122.3321
    assert result["city"] == "Seattle"
    assert result["country"] == "United States"
    assert calls[0][2]["User-Agent"] == geocoding.USER_AGENT
    assert calls[0][3] == (5, 15)


def test_geocode_city_raises_for_no_results(monkeypatch):
    monkeypatch.setattr(geocoding, "_request_nominatim", lambda city: [])
    geocoding._cached_geocode.cache_clear()

    with pytest.raises(DestinationNotFoundError):
        geocode_city("Nowhere")


def test_geocode_city_rejects_empty_destination():
    with pytest.raises(ValueError, match="Destination is required"):
        geocode_city(" ")
