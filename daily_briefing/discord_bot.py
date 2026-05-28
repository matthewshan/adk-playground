"""
Long-running Discord bot for bidirectional conversation with the daily briefing agent.

Handles two interaction modes:
  • Scheduled briefing — fires daily at 7 AM Eastern via discord.ext.tasks.
  • Conversational — each Discord user gets an independent ADK session with
    long-term memory persisted to Supabase.

Entry point:
    python -m daily_briefing.discord_bot

Setup and full configuration reference:
    docs/analysis/discord-bot-setup.md
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

# Load env before importing the agent so model selection and API keys are ready.
# Same pattern as daily_briefing/main.py.
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).parent / ".env")

import discord  # noqa: E402
from discord.ext import tasks  # noqa: E402
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions.in_memory_session_service import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from daily_briefing.agent import now_et, root_agent  # noqa: E402
from daily_briefing.memory.supabase_memory_service import SupabaseMemoryService  # noqa: E402

logger = logging.getLogger(__name__)

APP_NAME = "daily_briefing_bot"

# user_id used for the daily scheduled briefing — isolated from per-user scopes.
_SCHEDULER_USER_ID = "scheduler"

# Time the scheduled briefing fires each day (Eastern Time).
_BRIEFING_TIME = datetime.time(hour=7, minute=0, tzinfo=ZoneInfo("America/New_York"))

# Populated in main() before bot.run() so the event loop owns them.
_runner: Runner | None = None
_channel_id: int | None = None

# user_id (str) → ADK session_id (str)
_sessions: dict[str, str] = {}

# Per-user lock so rapid messages are queued, not parallelised.
_locks: dict[str, asyncio.Lock] = {}

intents = discord.Intents.default()
intents.message_content = True  # requires "Message Content Intent" in Developer Portal
bot = discord.Client(intents=intents)


# ---------------------------------------------------------------------------
# Startup check
# ---------------------------------------------------------------------------


def _check_supabase_config() -> bool:
    """Return True if Supabase is fully configured; log a warning and return False if not."""
    missing = [
        v for v in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") if not os.getenv(v)
    ]
    if missing:
        logger.warning(
            "Memory disabled: env var(s) not set: %s. "
            "Add them to .env to enable Supabase memory persistence.",
            ", ".join(missing),
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_cause(exc: BaseException) -> str:
    """One-line cause string for logs and user-facing error replies.

    Discord users see this instead of a generic "check the logs" so the actual
    failure is visible without `kubectl logs`.
    """
    msg = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


def _preview(text: str, limit: int = 120) -> str:
    """Single-line, length-capped preview of *text* for log lines."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _split_message(text: str, limit: int = 2000) -> list[str]:
    """Split *text* into Discord-safe chunks of at most *limit* characters.

    Prefers splitting on the last newline before the limit so Markdown
    formatting (bullet lists, bold headers) stays intact. Falls back to a
    hard split at *limit* when no newline exists in the window.

    Returns a list with at least one element (even for empty input).
    """
    if not text:
        return [""]

    chunks: list[str] = []
    while len(text) > limit:
        # Find the last newline within the allowed window.
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            # No newline — hard split at the limit.
            split_at = limit
        else:
            # Include the newline in the current chunk, skip it in the next.
            split_at += 1

        chunks.append(text[:split_at])
        text = text[split_at:]

    chunks.append(text)
    return chunks


async def _get_or_create_session(user_id: str) -> str:
    """Return the existing ADK session ID for *user_id*, creating one if needed."""
    if user_id not in _sessions:
        assert _runner is not None, "runner not initialised"
        session = await _runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
        )
        _sessions[user_id] = session.id
        logger.info("Created new session %s for user %s", session.id, user_id)
    return _sessions[user_id]


async def _run_agent(user_id: str, prompt: str) -> str:
    """Send *prompt* through the ADK agent for *user_id*'s session.

    Collects all text parts from every event and returns them joined.
    """
    assert _runner is not None, "runner not initialised"

    session_id = await _get_or_create_session(user_id)
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    )

    response_parts: list[str] = []
    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.text:
                response_parts.append(part.text)

    return "".join(response_parts) or "(No response from agent.)"


# ---------------------------------------------------------------------------
# Scheduled briefing task
# ---------------------------------------------------------------------------


@tasks.loop(time=_BRIEFING_TIME)
async def daily_briefing_task() -> None:
    """Fire the morning digest once a day at 7 AM ET and post it to the channel."""
    channel = bot.get_channel(_channel_id)  # type: ignore[arg-type]
    if channel is None:
        logger.error("Scheduled briefing: channel %d not found", _channel_id)
        return

    prompt = (
        f"Current date and time: {now_et()}\n\n"
        "Fetch weather for Grand Rapids MI, top news plus the latest cloud "
        "and AI news, NFL/MLB/CFL scores (highlight Detroit Lions, Toronto "
        "Blue Jays, Hamilton Tiger-Cats), and today's calendar events. "
        "Write the morning digest."
    )

    # Reset the scheduler session each day so each briefing runs with a clean
    # context window.  Reusing the same session across days accumulates the full
    # history of every prior briefing as LLM context, growing without bound.
    _sessions.pop(_SCHEDULER_USER_ID, None)

    logger.info("Firing scheduled morning briefing")
    started = time.monotonic()
    try:
        async with channel.typing():  # type: ignore[union-attr]
            response = await _run_agent(_SCHEDULER_USER_ID, prompt)
    except Exception as exc:
        elapsed = time.monotonic() - started
        cause = _fmt_cause(exc)
        logger.exception(
            "Scheduled briefing failed after %.1fs: %s", elapsed, cause
        )
        try:
            await channel.send(  # type: ignore[union-attr]
                f"⚠️ Scheduled briefing failed: `{cause}`"
            )
        except Exception:
            logger.exception("Could not send error message to channel")
        return

    elapsed = time.monotonic() - started
    logger.info(
        "Scheduled briefing succeeded in %.1fs (%d chars)", elapsed, len(response)
    )
    for chunk in _split_message(response):
        await channel.send(chunk)  # type: ignore[union-attr]


@daily_briefing_task.before_loop
async def _before_daily_briefing() -> None:
    """Wait for the bot to be fully connected before the first task iteration."""
    await bot.wait_until_ready()


# ---------------------------------------------------------------------------
# Discord event handlers
# ---------------------------------------------------------------------------


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s (ID: %d)", bot.user, bot.user.id)  # type: ignore[union-attr]
    logger.info("Listening in channel ID %d", _channel_id)
    logger.info("Scheduled briefing at %s daily", _BRIEFING_TIME.strftime("%H:%M %Z"))
    if not daily_briefing_task.is_running():
        daily_briefing_task.start()


@bot.event
async def on_message(message: discord.Message) -> None:
    # Ignore messages from bots (including ourselves) to prevent feedback loops.
    if message.author.bot:
        return

    # Ignore messages outside the configured channel.
    if message.channel.id != _channel_id:
        return

    # Ignore empty messages (e.g. image-only posts).
    prompt = message.content.strip()
    if not prompt:
        return

    # Use a string key so it's compatible with the scheduler's str user_id.
    user_id = str(message.author.id)

    logger.info(
        "Inbound from user %s (%d chars): %s",
        user_id,
        len(prompt),
        _preview(prompt),
    )

    # Serialise concurrent messages from the same user.
    lock = _locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        started = time.monotonic()
        # Show the typing indicator while the agent works (typically 3–10 s).
        async with message.channel.typing():
            try:
                response = await _run_agent(user_id, prompt)
            except Exception as exc:
                elapsed = time.monotonic() - started
                cause = _fmt_cause(exc)
                logger.exception(
                    "Agent error for user %s after %.1fs: %s",
                    user_id,
                    elapsed,
                    cause,
                )
                await message.channel.send(
                    f"⚠️ Something went wrong: `{cause}`"
                )
                return

        elapsed = time.monotonic() - started
        logger.info(
            "Agent reply to user %s in %.1fs (%d chars)",
            user_id,
            elapsed,
            len(response),
        )

        # Send the response in Discord-safe chunks (≤2000 chars each).
        for chunk in _split_message(response):
            await message.channel.send(chunk)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    global _runner, _channel_id

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        logger.error("DISCORD_BOT_TOKEN is not set. Aborting.")
        sys.exit(1)

    raw_channel = os.environ.get("DISCORD_BOT_CHANNEL_ID", "")
    if not raw_channel:
        logger.error("DISCORD_BOT_CHANNEL_ID is not set. Aborting.")
        sys.exit(1)
    _channel_id = int(raw_channel)

    # Only wire Supabase memory if both env vars are present.  Without them the
    # Runner gets memory_service=None and the bot degrades gracefully: sessions
    # still work, LoadMemoryTool is simply not available to the agent.
    supabase_ok = _check_supabase_config()
    memory_service = SupabaseMemoryService() if supabase_ok else None

    # Initialise the runner synchronously before handing control to discord.py's
    # event loop. Runner.__init__ is synchronous in ADK.
    _runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=InMemorySessionService(),
        artifact_service=InMemoryArtifactService(),
        memory_service=memory_service,
    )

    logger.info("Starting Discord bot (channel %d)…", _channel_id)
    # bot.run() creates and owns the asyncio event loop; no asyncio.run() wrapper needed.
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
