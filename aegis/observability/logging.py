"""AEGIS-1303: Structured Logging.

JSON-format structured logging with no PII exposure.
Uses Python's standard logging with a JSON formatter.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging.

    Output: one JSON object per line with fields:
    timestamp, level, message, logger, and any extras.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add structured fields from record extras
        for key in ("request_id", "action_type", "decision", "duration_ms", "domain"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value

        if record.exc_info and record.exc_info[1]:
            entry["exception"] = str(record.exc_info[1])

        return json.dumps(entry, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    """Configure AEGIS structured logging.

    Sets up JSON-format logging on the root 'aegis' logger.
    """
    aegis_logger = logging.getLogger("aegis")
    aegis_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not aegis_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        aegis_logger.addHandler(handler)
