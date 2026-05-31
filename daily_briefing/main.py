"""CLI debug runner — prints the morning digest to stdout.

Use this for local smoke-testing the agent pipeline without starting the
Discord bot.  The scheduled briefing in production is handled automatically
by discord_bot.py via discord.ext.tasks.

Run:
    python3 -m daily_briefing.main
"""

import asyncio
import logging
import sys
from pathlib import Path

# Allow running directly from either the repo root or the daily_briefing/ folder
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Must load env vars before importing the agent so model selection works correctly
_ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(_ENV_FILE)

from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions.in_memory_session_service import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from daily_briefing.agent import now_et, root_agent  # noqa: E402
from daily_briefing.log_config import configure_logging  # noqa: E402
from daily_briefing.memory.supabase_memory_service import SupabaseMemoryService  # noqa: E402

APP_NAME = "daily_briefing"
USER_ID = "scheduler"

logger = logging.getLogger(__name__)


async def run() -> None:
    configure_logging()
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=InMemorySessionService(),
        artifact_service=InMemoryArtifactService(),
        memory_service=SupabaseMemoryService(),
    )

    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[
                types.Part(
                    text=(
                        f"Current date and time: {now_et()}\n\n"
                        "Fetch weather for Grand Rapids MI, top news plus the latest cloud "
                        "and AI news, NFL/MLB/CFL scores (highlight Detroit Lions, Toronto "
                        "Blue Jays, Hamilton Tiger-Cats), and today's calendar events. "
                        "Write the morning digest."
                    )
                )
            ],
        ),
    ):
        if event.content:
            for part in event.content.parts or []:
                if part.text:
                    logger.info("%s", part.text)


if __name__ == "__main__":
    asyncio.run(run())
