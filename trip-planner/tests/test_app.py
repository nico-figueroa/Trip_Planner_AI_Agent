from pathlib import Path

import pydeck as pdk
import pytest
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


def test_generation_runs_planner_in_background_and_shows_result(monkeypatch):
    import time

    from utils import agent, openai_client, persistence

    class SlowPlanner:
        def __init__(self, **kwargs):
            pass

        def generate_trip_plan(self, **request):
            time.sleep(0.2)
            return {
                "destination": request["destination"],
                "duration": request["duration"],
                "location": {"latitude": 9.93, "longitude": -84.08},
                "pois": [],
                "itinerary": {
                    "destination": request["destination"],
                    "overview": "Generated overview.",
                    "travel_notes": "",
                    "daily_plan": [{"day": 1, "title": "Arrival", "activities": ["Rest"]}],
                },
                "trace": [],
            }

    saved_states = []
    monkeypatch.setattr(openai_client, "resolve_secret", lambda name: ("test-key", ".env"))
    monkeypatch.setattr(agent, "TripPlannerAgent", SlowPlanner)
    monkeypatch.setattr(persistence, "save_state", saved_states.append)
    monkeypatch.setattr(persistence, "load_state", lambda: {"active_itinerary": None})
    app_path = Path(__file__).resolve().parents[2] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    app.text_input[0].input("Costa Rica")
    next(button for button in app.button if button.label == "Generate itinerary").click().run()

    assert not app.exception
    assert not app.error
    assert any("Itinerary generated" in message.value for message in app.success)
    assert app.session_state["planner_state"]["active_itinerary"]["destination"] == "Costa Rica"
    assert saved_states == []  # Anonymous plans must never write shared local state.


def test_new_plan_replaces_stale_saved_selection_and_shows_dates(monkeypatch):
    from datetime import date

    from utils import agent, openai_client, persistence

    requests = []

    class Planner:
        def __init__(self, **kwargs):
            pass

        def generate_trip_plan(self, **request):
            requests.append(request)
            return {
                "destination": request["destination"],
                "duration": request["duration"],
                "start_date": request["start_date"].isoformat(),
                "location": {"latitude": 9.93, "longitude": -84.08},
                "pois": [],
                "itinerary": {
                    "destination": request["destination"],
                    "overview": "New plan.",
                    "travel_notes": "",
                    "daily_plan": [{"day": 1, "title": "Arrive", "activities": ["Rest"]}],
                },
                "trace": [],
            }

    old_plan = {
        "id": "old-plan",
        "destination": "Costa Rica",
        "duration": 1,
        "location": {"latitude": 9.93, "longitude": -84.08},
        "itinerary": {
            "destination": "Costa Rica",
            "overview": "Old plan.",
            "travel_notes": "",
            "daily_plan": [{"day": 1, "title": "Old day", "activities": ["Old"]}],
        },
    }
    monkeypatch.setattr(openai_client, "resolve_secret", lambda name: ("test-key", ".env"))
    monkeypatch.setattr(agent, "TripPlannerAgent", Planner)
    monkeypatch.setattr(persistence, "save_state", lambda state: None)
    monkeypatch.setattr(
        persistence,
        "load_state",
        lambda: {"active_itinerary": old_plan, "saved_itineraries": [old_plan]},
    )
    app_path = Path(__file__).resolve().parents[2] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    app.session_state["selected_plan"] = "old-plan"
    app.text_input[0].input("Costa Rica")
    app.date_input[0].set_value(date(2026, 12, 21))
    next(button for button in app.button if button.label == "Generate itinerary").click().run()

    assert not app.exception
    assert requests[0]["start_date"] == date(2026, 12, 21)
    labels = [expander.label for expander in app.expander]
    assert "Day 1 · Mon Dec 21, 2026: Arrive" in labels
    assert all("Old day" not in label for label in labels)


def test_saved_itinerary_renders_without_errors(monkeypatch):
    decks = []
    original_deck = pdk.Deck

    def capture_deck(*args, **kwargs):
        decks.append(kwargs)
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
        "stops": [{"name": "Tacoma", "latitude": 47.2529, "longitude": -122.4443}],
        "pois": [
            {
                "name": "City Museum <b>untrusted markup</b>",
                "category": "Museum",
                "address": "100 Main Street, Seattle",
                "latitude": 47.607,
                "longitude": -122.331,
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
    assert list(app.dataframe[0].value.columns) == ["Name", "Category", "Address", "More information"]
    assert app.dataframe[0].value["Address"][0] == "100 Main Street, Seattle"
    assert any("powered by [Geoapify]" in caption.value for caption in app.caption)
    assert [element.label for element in app.get("download_button")] == ["Save as PDF", "Export plan JSON"]
    assert [deck["tooltip"] for deck in decks] == [{"text": "{name}\n{category}"}]
    view = decks[0]["initial_view_state"]
    assert 47.2529 < view.latitude < 47.6062
    assert 7 < view.zoom < 12
    layers = decks[0]["layers"]
    assert layers[0].type == "PathLayer"
    import json

    assert json.loads(layers[1].to_json())["radiusUnits"] == "meters"


def test_date_range_adjusts_number_widget_and_passes_effective_duration(monkeypatch):
    from datetime import date
    from utils import agent, openai_client

    requests = []

    class Planner:
        def __init__(self, **kwargs):
            pass

        def generate_trip_plan(self, **request):
            requests.append(request)
            return {
                "destination": request["destination"], "duration": request["duration"],
                "location": {"latitude": 9, "longitude": -84}, "pois": [],
                "itinerary": {
                    "destination": request["destination"], "overview": "Trip", "travel_notes": "Notes",
                    "daily_plan": [{"day": day, "title": "Day", "activities": ["Rest"]} for day in range(1, request["duration"] + 1)],
                },
            }

    monkeypatch.setattr(agent, "TripPlannerAgent", Planner)
    monkeypatch.setattr(openai_client, "get_api_key", lambda: "test-key")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py"), default_timeout=10).run()
    app.segmented_control(key="date_mode").set_value("Both").run()
    app.text_input(key="destination").set_value("Costa Rica")
    app.date_input(key="start_date").set_value(date(2026, 12, 21))
    app.date_input(key="end_date").set_value(date(2027, 1, 8))
    next(button for button in app.button if button.label == "Generate itinerary").click().run()
    assert not app.exception
    assert requests[0]["duration"] == 19
    assert app.number_input(key="duration").value == 19
    assert any("automatically adjusted" in info.value for info in app.info)
    active = app.session_state["planner_state"]["active_itinerary"]["id"]
    app.selectbox(key=f"day_filter_{active}").select(4).run()
    assert not app.exception
    assert app.session_state["planner_state"]["active_itinerary"]["id"] == active
    assert len(app.session_state["planner_state"]["active_itinerary"]["itinerary"]["daily_plan"]) == 19
    app.selectbox(key=f"day_filter_{active}").select(None).run()
    assert not app.exception
    assert len([item for item in app.expander if item.label.startswith("Day ")]) == 19


@pytest.mark.parametrize("duplicate", [False, True])
def test_alternatives_are_explicit_distinct_and_keep_original(monkeypatch, duplicate):
    import copy
    from utils import agent

    original = {
        "id": "original", "destination": "Seattle", "duration": 1,
        "location": {"latitude": 47, "longitude": -122}, "pois": [],
        "itinerary": {
            "destination": "Seattle", "overview": "Original", "travel_notes": "Notes",
            "daily_plan": [{"day": 1, "title": "Original day", "activities": ["Rest"]}],
        },
    }
    calls = []

    class Planner:
        def __init__(self, **kwargs):
            pass

        def generate_trip_plan(self, **request):
            calls.append(request)
            result = copy.deepcopy(original)
            if not duplicate:
                result["itinerary"]["daily_plan"][0]["title"] = f"Alternative day {len(calls)}"
            return result

    monkeypatch.setattr(agent, "TripPlannerAgent", Planner)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py"), default_timeout=10)
    app.session_state["planner_state"] = {
        "active_itinerary": copy.deepcopy(original), "session_plans": [copy.deepcopy(original)],
    }
    app.session_state["current_plan"] = copy.deepcopy(original)
    app.run()
    assert not calls
    app.checkbox(key="alternatives_enabled").check().run()
    next(button for button in app.button if button.label == "Generate two alternative plans").click().run()
    assert not app.exception
    plans = app.session_state["planner_state"]["session_plans"]
    assert plans[-1] == original
    if duplicate:
        assert len(calls) == 1 and len(plans) == 1
        assert any("duplicate alternative" in error.value for error in app.error)
    else:
        assert len(calls) == 2 and len(plans) == 3
        assert len({plan["itinerary"]["daily_plan"][0]["title"] for plan in plans}) == 3


def test_empty_account_load_preserves_unsaved_session_plan(monkeypatch):
    from utils import accounts

    class Store:
        def load(self, identity):
            return {}

        def stats(self):
            return {"total": 0, "positive": 0, "negative": 0}

    monkeypatch.setattr(accounts, "current_identity", lambda: accounts.Identity("a" * 64))
    monkeypatch.setattr(accounts, "get_store", lambda: Store())
    plan = {
        "id": "unsaved", "destination": "Seattle", "duration": 1,
        "location": {"latitude": 47, "longitude": -122},
        "itinerary": {
            "destination": "Seattle", "overview": "Trip", "travel_notes": "Notes",
            "daily_plan": [{"day": 1, "title": "Rest", "activities": ["Rest"]}],
        },
    }
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py"), default_timeout=10)
    app.session_state["planner_state"] = {"active_itinerary": plan}
    app.session_state["current_plan"] = plan
    app.run()
    next(button for button in app.button if button.label == "Load my saved plans").click().run()
    assert not app.exception
    assert app.session_state["current_plan"]["id"] == "unsaved"
    assert any("session plan is unchanged" in info.value for info in app.info)
