import json

import pytest

from utils import persistence


@pytest.fixture
def temporary_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(persistence, "DATA_DIR", data_dir)
    monkeypatch.setattr(persistence, "STATE_FILE", data_dir / "app_state.json")
    monkeypatch.setattr(persistence, "FEEDBACK_FILE", data_dir / "feedback.jsonl")
    monkeypatch.setattr(persistence, "LOG_FILE", data_dir / "log.json")
    return data_dir


def test_save_and_load_state(temporary_data_dir):
    data = {"active_itinerary": {"destination": "Seattle"}}

    persistence.save_state(data)

    assert persistence.load_state() == data


def test_missing_state_returns_empty_object(temporary_data_dir):
    assert persistence.load_state() == {}


def test_corrupt_state_returns_empty_object(temporary_data_dir):
    persistence.STATE_FILE.parent.mkdir(parents=True)
    persistence.STATE_FILE.write_text("{", encoding="utf-8")

    assert persistence.load_state() == {}


def test_rejects_paths_outside_data_directory(temporary_data_dir, monkeypatch):
    monkeypatch.setattr(persistence, "STATE_FILE", temporary_data_dir.parent / "outside.json")

    with pytest.raises(ValueError, match="inside the application data directory"):
        persistence.save_state({})


def test_feedback_is_appended_as_jsonl(temporary_data_dir):
    persistence.append_feedback({"rating": "positive", "comment": "Great"})
    persistence.append_feedback({"rating": "negative", "comment": "Too much walking"})

    lines = persistence.FEEDBACK_FILE.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["rating"] for line in lines] == ["positive", "negative"]
