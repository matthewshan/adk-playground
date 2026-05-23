"""Local test runner — identical to main.py but prints the digest to stdout
instead of posting to Discord. Safe to run behind a firewall."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from google.adk import Agent  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from daily_briefing.tools.calendar_events import get_calendar_events  # noqa: E402
from daily_briefing.tools.news import get_news  # noqa: E402
from daily_briefing.tools.sports import get_sports_scores  # noqa: E402
from daily_briefing.tools.weather import get_weather  # noqa: E402

APP_NAME = "daily_briefing_test"
USER_ID = "local"


def print_briefing(message: str) -> str:
    """Console stand-in for send_discord: prints the briefing to stdout."""
    print("\n" + "=" * 60)
    print(message)
    print("=" * 60 + "\n")
    return "Printed"


_backend = os.getenv("BACKEND", "gemini").lower()
if _backend == "ollama":
    _ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    _model = LiteLlm(model=f"ollama_chat/{_ollama_model}")
else:
    _model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

_instruction = (Path(__file__).parent.parent / "instruction.md").read_text(encoding="utf-8")

test_agent = Agent(
    name="daily_briefing",
    model=_model,
    description="Daily morning digest agent.",
    instruction=_instruction,
    tools=[get_weather, get_news, get_sports_scores, get_calendar_events, print_briefing],
)


async def run() -> None:
    runner = InMemoryRunner(agent=test_agent, app_name=APP_NAME)
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
                        "Fetch weather for Grand Rapids MI, top news plus the latest cloud "
                        "and AI news, NFL/MLB/CFL scores (highlight Detroit Lions, Toronto "
                        "Blue Jays, Hamilton Tiger-Cats), and today's calendar events. "
                        "Write and send the morning digest."
                    )
                )
            ],
        ),
    ):
        if event.content:
            for part in event.content.parts or []:
                if part.text:
                    print(part.text)


if __name__ == "__main__":
    asyncio.run(run())
