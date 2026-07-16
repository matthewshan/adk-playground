"""pc-broker wake helper — wakes the gaming PC before Ollama-backed agent runs.

The pc-broker LLM proxy returns 503 unless the PC is awake and Ollama is
serving, so headless callers must wake it first: POST /api/power/on, then
poll GET /api/status until state == "ready". Active only when BACKEND=ollama
and PC_BROKER_URL is set; a no-op otherwise (plain local Ollama, gemini,
github).
"""

import asyncio
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

_POLL_SECONDS = 5.0
_DEFAULT_TIMEOUT_SECONDS = 300.0
_HTTP_TIMEOUT = 10.0


def _base_url() -> str | None:
    """Broker base URL, or None when wake handling doesn't apply."""
    if os.getenv("BACKEND", "gemini").lower() != "ollama":
        return None
    url = os.getenv("PC_BROKER_URL", "").strip().rstrip("/")
    return url or None


def _state(base: str) -> str:
    resp = requests.get(f"{base}/api/status", timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("state", "")


def _power_on(base: str) -> None:
    requests.post(f"{base}/api/power/on", timeout=_HTTP_TIMEOUT).raise_for_status()


def _wake_and_wait(base: str, timeout: float) -> None:
    if _state(base) == "ready":
        return

    logger.info("Waking gaming PC via pc-broker at %s", base)
    _power_on(base)

    deadline = time.monotonic() + timeout
    while True:
        state = _state(base)
        if state == "ready":
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f"PC not ready after {int(timeout)}s (last state: {state!r})")
        # Broker gave up on its own reachability window (or errored). A new
        # wake request from these states re-sends the WoL packet, so keep
        # retrying until *our* deadline — the 2026-07-16 briefing died on a
        # single unanswered wake.
        if state in ("timeout", "error"):
            logger.warning("pc-broker reported %r — re-requesting wake", state)
            _power_on(base)
        time.sleep(_POLL_SECONDS)


async def ensure_ready(timeout: float | None = None) -> None:
    """Block until the broker-fronted Ollama is ready to serve.

    Raises TimeoutError / RuntimeError / requests.RequestException on failure
    so callers surface the cause instead of a bare LLM 503.
    """
    base = _base_url()
    if base is None:
        return
    if timeout is None:
        timeout = float(os.getenv("PC_BROKER_WAKE_TIMEOUT", str(_DEFAULT_TIMEOUT_SECONDS)))
    started = time.monotonic()
    # requests is sync — run the wait off the event loop thread.
    await asyncio.to_thread(_wake_and_wait, base, timeout)
    elapsed = time.monotonic() - started
    if elapsed > _POLL_SECONDS:
        logger.info("pc-broker ready after %.1fs", elapsed)
