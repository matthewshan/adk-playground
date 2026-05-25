"""
Long-running Discord bot for bidirectional conversation with the daily briefing agent.

Each Discord user who messages in the configured channel gets their own independent
conversation session with the ADK agent. Context is maintained in-memory for the
lifetime of the bot process.

Entry point:
    python -m daily_briefing.discord_bot

Required environment variables:
    DISCORD_BOT_TOKEN      — Bot token from the Discord Developer Portal
    DISCORD_BOT_CHANNEL_ID — Channel ID the bot listens in (integer)

    All other variables from .env.example are also required (Gemini key,
    GNews key, etc.) since the same agent runs here as in the CronJob.

Setup (one-time, in Discord Developer Portal):
    1. Create an application at https://discord.com/developers/applications
    2. Add a Bot to the application and copy its token → DISCORD_BOT_TOKEN
    3. Under Bot → Privileged Gateway Intents, enable "Message Content Intent"
    4. Generate an invite URL with scopes: bot
       Permissions: Send Messages, Read Message History
    5. Invite the bot to your server

Session design:
    - Per-user: each Discord user_id maps to its own ADK session, so Alice and
      Bob have independent conversation histories even in the same channel.
    - Sessions live in RAM; they reset when the bot process restarts.
    - A per-user asyncio.Lock serialises rapid back-to-back messages from the
      same user so the agent never processes two turns concurrently for one session.

Future memory upgrade:
    Swap InMemoryRunner for Runner(..., memory_service=YourVectorStore()) in main().
    The user_id key (Discord snowflake) and the _sessions / _locks dicts are
    unchanged — only the runner constructor differs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Load env before importing the agent so model selection and API keys are ready.
# Same pattern as daily_briefing/main.py.
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).parent / ".env")

import discord  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from daily_briefing.agent import root_agent  # noqa: E402

logger = logging.getLogger(__name__)

APP_NAME = "daily_briefing_bot"

# Populated in main() before bot.run() so the event loop owns them.
_runner: InMemoryRunner | None = None
_channel_id: int | None = None

# user_id (Discord snowflake int) → ADK session_id (str)
_sessions: dict[int, str] = {}

# Per-user lock so rapid messages are queued, not parallelised.
_locks: dict[int, asyncio.Lock] = {}

intents = discord.Intents.default()
intents.message_content = True  # requires "Message Content Intent" in Developer Portal
bot = discord.Client(intents=intents)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


async def _get_or_create_session(user_id: int) -> str:
    """Return the existing ADK session ID for *user_id*, creating one if needed."""
    if user_id not in _sessions:
        assert _runner is not None, "runner not initialised"
        session = await _runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=str(user_id),
        )
        _sessions[user_id] = session.id
        logger.info("Created new session %s for user %d", session.id, user_id)
    return _sessions[user_id]


async def _run_agent(user_id: int, prompt: str) -> str:
    """Send *prompt* through the ADK agent for *user_id*'s session.

    Mirrors the run_prompt() pattern from minimal_ollama_adk/main.py.
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
        user_id=str(user_id),
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
# Discord event handlers
# ---------------------------------------------------------------------------


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s (ID: %d)", bot.user, bot.user.id)  # type: ignore[union-attr]
    logger.info("Listening in channel ID %d", _channel_id)


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

    user_id = message.author.id

    # Serialise concurrent messages from the same user.
    lock = _locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        # Show the typing indicator while the agent works (typically 3–10 s).
        async with message.channel.typing():
            try:
                response = await _run_agent(user_id, prompt)
            except Exception:
                logger.exception("Agent error for user %d", user_id)
                await message.channel.send(
                    "⚠️ Something went wrong. Please try again."
                )
                return

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

    # Initialise the runner synchronously before handing control to discord.py's
    # event loop. InMemoryRunner.__init__ is synchronous in ADK.
    _runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)

    logger.info("Starting Discord bot (channel %d)…", _channel_id)
    # bot.run() creates and owns the asyncio event loop; no asyncio.run() wrapper needed.
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
