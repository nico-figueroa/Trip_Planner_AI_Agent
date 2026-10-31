from pathlib import Path

import pydeck as pdk
from streamlit.testing.v1 import AppTest


def test_root_streamlit_entrypoint_renders_without_errors():
    app_path = Path(__file__).resolve().parents[2] / "app.py"

    app = AppTest.from_file(str(app_path), default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "AI Trip Planner"
    assert not app.sidebar.text_input
    assert not app.sidebar.button
    assert all(button.label != "Test OpenAI connection" for button in app.button)


def test_generation_without_configured_key_has_actionable_error(monkeypatch):
    from utils import openai_client

    monkeypatch.setattr(openai_client, "resolve_secret", lambda name: (None, None))
    app_path = Path(__file__).resolve().parents[2] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    next(button for button in app.button if button.label == "Generate itinerary").click().run()

    assert not app.exception
    assert any("OPENAI_API_KEY" in error.value for error in app.error)
    assert all("sidebar" not in error.value for error in app.error)


def test_saved_itinerary_renders_without_errors(monkeypatch):
    tooltips = []
    original_deck = pdk.Deck

    def capture_deck(*args, **kwargs):
        tooltips.append(kwargs["tooltip"])
        return original_deck(*args, **kwargs)

    monkeypatch.setattr(pdk, "Deck", capture_deck)
    app_path = Path(__file__).resolve().parents[2] / "app.py"
    plan = {
        "id": "test-plan",
        "destination": "Seattle",
        "created_at": "2026-10-31T12:00:00+00:00",
        "duration": 1,
        "location": {
            "latitude": 47.6062,
            "longitude": -122.3321,
            "city": "Seattle",
        },
        "pois": [
            {
                "name": "City Museum <b>untrusted markup</b>",
                "category": "Museum",
                "latitude": 47.607,
                "longitude": -122.331,
                "source": "Geoapify",
            }
        ],
        "itinerary": {
            "destination": "Seattle",
            "overview": "A museum visit.",
            "travel_notes": "Check the opening time.",
            "daily_plan": [
                {
                    "day": 1,
                    "title": "Museum day",
                    "activities": ["Visit City Museum"],
                }
            ],
        },
        "trace": [],
    }
    app = AppTest.from_file(str(app_path), default_timeout=10)
    app.session_state["planner_state"] = {
        "active_itinerary": plan,
        "saved_itineraries": [],
    }
    app.session_state["current_plan"] = plan

    app.run()

    assert not app.exception
    assert app.dataframe
    assert any("Powered by" in caption.value for caption in app.caption)
    assert tooltips == [{"text": "{name}\n{category}"}]
