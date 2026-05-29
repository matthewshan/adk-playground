from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.adk.tools.load_memory_tool import LoadMemoryTool

from daily_briefing.models import make_model
from daily_briefing.tools.calendar_events import get_calendar_events
from daily_briefing.tools.news import get_news
from daily_briefing.tools.sports import get_game_plays, get_sports_scores
from daily_briefing.tools.weather import get_weather

_instruction = (Path(__file__).parent / "instruction.md").read_text(encoding="utf-8")


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
    is configured on the Runner, or if Supabase credentials are absent, the
    error is silently swallowed so local / test runs still work.
    """
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        # memory_service not configured, Supabase env vars missing, or
        # transient network error — skip silently.
        pass


def make_agent(name: str = "daily_briefing") -> Agent:
    """Create a daily-briefing Agent.

    The agent composes text and returns it — delivery to Discord is handled
    by the caller (discord_bot.py posts via channel.send()).

    Args:
        name: ADK agent name; override to isolate test sessions from production.
    """
    return Agent(
        name=name,
        model=make_model(),
        description="Daily morning digest agent.",
        instruction=_instruction,
        tools=[
            get_weather,
            get_news,
            get_sports_scores,
            get_game_plays,
            get_calendar_events,
            LoadMemoryTool(),  # LLM can search past briefings on demand
            GoogleSearchTool(bypass_multi_tools_limit=True),  # Gemini-only; no-op on Ollama
        ],
        after_agent_callback=_save_to_memory,
    )


root_agent = make_agent()
