"""Safe JSON persistence for active/saved itineraries and user feedback."""

from __future__ import annotations

import json
import logging
import os
import sys # System-specific parameters and functions, used for error output
import tempfile # Temporary file creation for atomic writes
import threading # Thread-safe lock for atomic file writes
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
STATE_FILE = DATA_DIR / "app_state.json"
FEEDBACK_FILE = DATA_DIR / "feedback.jsonl"
LOG_FILE = DATA_DIR / "log.json"
_write_lock = threading.RLock() # Reentrant lock to ensure thread-safe writes to JSON files

# Internal helper to ensure persistence paths remain within the data directory
def _safe_data_path(path: Path) -> Path:
    data_directory = DATA_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_path == data_directory or data_directory not in resolved_path.parents:
        raise ValueError("Persistence paths must remain inside the application data directory.")
    return resolved_path

# Internal helper to atomically write JSON data to a file
def _write_json(path: Path, data: Any) -> None:
    path = _safe_data_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    with _write_lock:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, path)
        except (OSError, TypeError, ValueError):
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise


def save_state(data: dict[str, Any]) -> None:
    """Atomically save application state to its configured JSON file."""
    if not isinstance(data, dict):
        raise ValueError("Application state must be a JSON object.")
    try:
        _write_json(STATE_FILE, data)
    except (OSError, TypeError, ValueError):
        logger.exception("Could not save application state.")
        raise


def append_log_event(event: dict[str, Any], limit: int = 200) -> None:
    """Atomically retain a bounded JSON event history without recursive logging."""
    if not isinstance(event, dict) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Log events must be objects and the history limit must be positive.")
    path = _safe_data_path(LOG_FILE)
    with _write_lock:
        try:
            with path.open("r", encoding="utf-8") as file:
                events = json.load(file)
            if not isinstance(events, list):
                raise ValueError("Log history must be a JSON array.")
        except FileNotFoundError:
            events = []
        except (json.JSONDecodeError, UnicodeError, ValueError):
            print("Application log history is corrupt; resetting log.json.", file=sys.stderr)
            events = []
        events.append(event)
        _write_json(path, events[-limit:])


def load_state() -> dict[str, Any]:
    """Load state, returning an empty object for a missing or corrupt file."""
    path = _safe_data_path(STATE_FILE)
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Could not load application state (%s).", type(error).__name__)
        return {}

    if not isinstance(data, dict):
        logger.warning("Application state has an invalid top-level type.")
        return {}
    return data


def append_feedback(feedback: dict[str, Any]) -> None:
    """Append one JSONL feedback record without replacing prior submissions."""
    if not isinstance(feedback, dict):
        raise ValueError("Feedback must be a JSON object.")

    path = _safe_data_path(FEEDBACK_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _write_lock:
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(feedback, ensure_ascii=False) + "\n")
                file.flush()
                os.fsync(file.fileno())
    except (OSError, TypeError, ValueError):
        logger.exception("Could not append user feedback.")
        raise
