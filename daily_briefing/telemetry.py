"""Langfuse tracing setup for the daily-briefing agent.

Call :func:`configure_telemetry` at startup **before importing
:mod:`daily_briefing.agent`** — that module builds ``root_agent`` at import
time, and the OpenInference instrumentor has to patch ADK first.

Disabled unless ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set, so
local runs and CI are unaffected.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_telemetry() -> None:
    """Instrument ADK to emit traces to Langfuse; no-op if unconfigured."""
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        logger.debug("Langfuse keys unset — tracing disabled")
        return

    try:
        from langfuse import get_client
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
    except ImportError:
        logger.warning("Langfuse keys set but packages missing — tracing disabled")
        return

    # An unreachable Langfuse must not take the briefing down with it.
    try:
        if not get_client().auth_check():
            logger.warning("Langfuse auth check failed — tracing disabled")
            return
        GoogleADKInstrumentor().instrument()
    except Exception:
        logger.warning("Langfuse init failed — tracing disabled", exc_info=True)
        return

    logger.info(
        "Langfuse tracing enabled (%s)",
        os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    )
