"""Credential-safe terminal logging and a bounded JSON event history."""

from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timezone

from utils.storage.persistence import append_log_event


class SafeFormatter(logging.Formatter):
    """Exclude raw exception bodies and redact credential-shaped message values."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        message = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", message)
        message = re.sub(
            r"""(?i)((?:api[_-]?key|authorization)["']?\s*[:=]\s*)"""
            r"""(?:["']?(?:Bearer\s+)?[^"'\s,}]+["']?)""",
            r"\1[REDACTED]",
            message,
        )
        message = message.replace("\r", " ").replace("\n", " ")[:1000]
        if record.exc_info and record.exc_info[0]:
            message += f" ({record.exc_info[0].__name__})"
        return message


class JSONLogHandler(logging.Handler):
    """Persist sanitized application events; surface file failures on stderr."""

    def emit(self, record: logging.LogRecord) -> None:
        formatter = self.formatter or SafeFormatter()
        event = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": formatter.format(record),
        }
        try:
            append_log_event(event)
        except (OSError, TypeError, ValueError):
            print(
                "Could not write data/log.json; application logging continues on stderr.",
                file=sys.stderr,
            )


def configure_logging() -> None:
    """Install application-only handlers once, including across Streamlit reruns."""
    logger = logging.getLogger("utils")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if any(isinstance(handler, JSONLogHandler) for handler in logger.handlers):
        return
    formatter = SafeFormatter()
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    history = JSONLogHandler()
    history.setFormatter(formatter)
    logger.addHandler(console)
    logger.addHandler(history)
