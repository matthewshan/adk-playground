"""Local test runner — prints the digest to stdout instead of posting to Discord.
Safe to run behind a firewall.

Differences from main.py / the production bot:
  - Uses a separate app_name ("daily_briefing_test") to isolate Supabase memory
    from the production scope.
  - Prints all agent text output directly to stdout; no delivery tool needed.
"""

import asyncio
import sys
from pathlib import Path

# Force UTF-8 output so emoji/Unicode in the briefing don't crash on Windows
# (default cp1252 terminal codec cannot encode most Unicode characters).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions.in_memory_session_service import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from daily_briefing.agent import make_agent, now_et  # noqa: E402
from daily_briefing.memory.supabase_memory_service import SupabaseMemoryService  # noqa: E402

APP_NAME = "daily_briefing_test"
USER_ID = "local"

# Separate agent name keeps test sessions out of the production memory scope.
test_agent = make_agent(name=APP_NAME)


async def run() -> None:
    runner = Runner(
        agent=test_agent,
        app_name=APP_NAME,
        session_service=InMemorySessionService(),
        artifact_service=InMemoryArtifactService(),
        # Separate memory namespace from production so test runs don't
        # pollute the real scheduler's memories.
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
                    print(part.text, flush=True)

    # Session persistence is handled automatically by the agent's
    # after_agent_callback (_save_to_memory in agent.py).


if __name__ == "__main__":
    asyncio.run(run())
