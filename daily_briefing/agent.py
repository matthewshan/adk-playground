import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.load_memory_tool import LoadMemoryTool

from daily_briefing.tools.calendar_events import get_calendar_events
from daily_briefing.tools.discord_webhook import send_discord
from daily_briefing.tools.news import get_news
from daily_briefing.tools.sports import get_sports_scores
from daily_briefing.tools.weather import get_weather

_instruction = (Path(__file__).parent / "instruction.md").read_text(encoding="utf-8")

_backend = os.getenv("BACKEND", "gemini").lower()
if _backend == "ollama":
    _ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    _model = LiteLlm(model=f"ollama_chat/{_ollama_model}")
else:
    _model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


def now_et() -> str:
    """Current date and time in Eastern Time, formatted for the agent prompt."""
    now = datetime.now(ZoneInfo("America/New_York"))
    hour = now.hour % 12 or 12
    ampm = "AM" if now.hour < 12 else "PM"
    return f"{now.strftime('%A, %B')} {now.day}, {now.year} at {hour}:{now.strftime('%M')} {ampm} ET"


async def _save_to_memory(callback_context: CallbackContext) -> None:
    """Persist the completed session to the memory service for future recall.

    Registered as ``after_agent_callback`` so the ADK framework calls this
    automatically at the end of every agent invocation.  If no memory service
    is configured on the Runner, the error is silently swallowed so local /
    test runs without Supabase still work.
    """
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        # memory_service not configured on this Runner — skip silently.
        pass


def make_agent(output_tool=send_discord, name: str = "daily_briefing") -> Agent:
    """Create a daily-briefing Agent, swapping in a different output tool if needed.

    Args:
        output_tool: Callable registered as the last tool; defaults to send_discord.
                     Pass a stub (e.g. print_briefing) for local smoke tests.
        name: ADK agent name; override to isolate test sessions from production.
    """
    return Agent(
        name=name,
        model=_model,
        description="Daily morning digest agent.",
        instruction=_instruction,
        tools=[
            get_weather,
            get_news,
            get_sports_scores,
            get_calendar_events,
            output_tool,
            LoadMemoryTool(),  # LLM can search past briefings on demand
        ],
        after_agent_callback=_save_to_memory,
    )


root_agent = make_agent()
