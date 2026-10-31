import json
import logging

import pytest

from utils import logging_config, persistence


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "DATA_DIR", tmp_path)
    path = tmp_path / "log.json"
    monkeypatch.setattr(persistence, "LOG_FILE", path)
    return path


def test_log_history_is_bounded_valid_json(log_path):
    for index in range(205):
        persistence.append_log_event({"message": f"event {index}"})

    assert json.loads(log_path.read_text(encoding="utf-8")) == [
        {"message": f"event {index}"} for index in range(5, 205)
    ]


def test_corrupt_log_is_reported_and_recovers(log_path, capsys):
    log_path.write_text("not json", encoding="utf-8")

    persistence.append_log_event({"message": "recovered"})

    assert "corrupt" in capsys.readouterr().err
    assert json.loads(log_path.read_text(encoding="utf-8")) == [{"message": "recovered"}]


def test_json_handler_redacts_keys_and_omits_exception_bodies(log_path):
    handler = logging_config.JSONLogHandler()
    handler.setFormatter(logging_config.SafeFormatter())
    record = logging.LogRecord(
        "utils.test",
        logging.ERROR,
        __file__,
        1,
        'API failure sk-test-secret apiKey=geoapify-test-secret '
        'Authorization: Bearer private-token "apiKey": "quoted-private-token"',
        (),
        (RuntimeError, RuntimeError("private provider body"), None),
    )

    handler.handle(record)

    message = json.loads(log_path.read_text(encoding="utf-8"))[0]["message"]
    assert "sk-test-secret" not in message
    assert "geoapify-test-secret" not in message
    assert "private-token" not in message
    assert "private provider body" not in message
    assert "RuntimeError" in message


def test_log_path_cannot_escape_data_directory(log_path, tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "LOG_FILE", tmp_path.parent / "outside-log.json")

    with pytest.raises(ValueError, match="inside the application data directory"):
        persistence.append_log_event({"message": "should not be written"})


def test_handler_write_failure_is_visible_and_does_not_crash(monkeypatch, capsys):
    def fail_write(event):
        raise PermissionError("not writable")

    monkeypatch.setattr(logging_config, "append_log_event", fail_write)
    handler = logging_config.JSONLogHandler()
    handler.handle(logging.LogRecord("utils.test", logging.ERROR, __file__, 1, "failed", (), None))

    assert "logging continues on stderr" in capsys.readouterr().err


def test_logging_configuration_is_idempotent(log_path):
    logger = logging.getLogger("utils")
    original_handlers = logger.handlers[:]
    original_level, original_propagate = logger.level, logger.propagate
    logger.handlers = []
    try:
        logging_config.configure_logging()
        logging_config.configure_logging()
        logger.warning("Test application event.")

        assert len(logger.handlers) == 2
        assert len(json.loads(log_path.read_text(encoding="utf-8"))) == 1
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate
