import os
from pathlib import Path

from google.adk import Agent

from daily_briefing.tools import (
    get_calendar_events,
    get_news,
    get_sports_scores,
    get_weather,
    send_discord,
)

_instruction = (Path(__file__).parent / "instruction.md").read_text(encoding="utf-8")

root_agent = Agent(
    name="daily_briefing",
    model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    description="Daily morning digest agent.",
    instruction=_instruction,
    tools=[get_weather, get_news, get_sports_scores, get_calendar_events, send_discord],
)
