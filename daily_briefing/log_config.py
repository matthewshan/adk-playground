"""Central logging setup for the daily-briefing app.

Both ``discord_bot.py`` and ``main.py`` call :func:`configure_logging` at
startup so the log format and level are consistent across the bot, the CLI
debug runner, and the smoke tests.

Level is read from the ``LOG_LEVEL`` env var (default ``INFO``). The agent
callbacks in :mod:`daily_briefing.logging_callbacks` log one compact line per
prompt / response / tool call at INFO; DEBUG just adds stdlib-level chatter,
not extra payload dumps.
"""

from __future__ import annotations

import logging
import os

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Third-party loggers that get noisy at DEBUG and rarely matter for agent
# debugging — clamped to INFO regardless of the app-wide level.
_NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "discord", "google_genai")


def configure_logging() -> None:
    """Configure root logging from ``LOG_LEVEL``; clamp known noisy libs."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=_LOG_FORMAT)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)


def preview(text: str, limit: int = 120) -> str:
    """Single-line, length-capped preview of *text* for log lines."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
