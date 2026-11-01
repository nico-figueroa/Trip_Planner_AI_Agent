"""Keep offline tests away from real user files, credentials, and databases."""

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    from utils.storage import accounts, persistence

    monkeypatch.setattr(accounts, "resolve_secret", lambda name: (None, None))
    monkeypatch.setattr(persistence, "DATA_DIR", tmp_path)
    monkeypatch.setattr(persistence, "STATE_FILE", tmp_path / "app_state.json")
    monkeypatch.setattr(persistence, "FEEDBACK_FILE", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(persistence, "LOG_FILE", tmp_path / "log.json")
