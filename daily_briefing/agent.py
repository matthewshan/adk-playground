from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.adk.tools.load_memory_tool import LoadMemoryTool

from daily_briefing.context_trim import make_trimmer
from daily_briefing.models import make_model, request_token_limit, supports_google_search
from daily_briefing.tools.calendar_events import get_calendar_events
from daily_briefing.tools.news import get_news
from daily_briefing.tools.sports import get_game_plays, get_sports_scores
from daily_briefing.tools.weather import get_weather
from daily_briefing.tools.web_search import web_search

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
    tools = [
        get_weather,
        get_news,
        get_sports_scores,
        get_game_plays,
        get_calendar_events,
        LoadMemoryTool(),  # search past briefings on demand
    ]
    # google_search is native-Gemini-only; ADK raises for LiteLLM backends.
    # Non-Gemini backends get the portable Tavily-backed web_search instead.
    if supports_google_search():
        tools.append(GoogleSearchTool(bypass_multi_tools_limit=True))
    else:
        tools.append(web_search)

    # On backends with a hard request-size cap (GitHub Models), keep each
    # request under the limit by trimming session history before it's sent.
    limit = request_token_limit()
    before_model_callback = make_trimmer(limit) if limit else None

    return Agent(
        name=name,
        model=make_model(),
        description="Daily morning digest agent.",
        instruction=_instruction,
        tools=tools,
        before_model_callback=before_model_callback,
        after_agent_callback=_save_to_memory,
    )


root_agent = make_agent()
