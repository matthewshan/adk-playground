import os
from pathlib import Path

from google.adk import Agent

from daily_briefing.tools.calendar_events import get_calendar_events
from daily_briefing.tools.discord_webhook import send_discord
from daily_briefing.tools.news import get_news
from daily_briefing.tools.sports import get_sports_scores
from daily_briefing.tools.weather import get_weather

_instruction = """
You are a friendly personal assistant delivering a daily morning briefing for someone in Grand Rapids, MI.

Call each tool to collect the data, then compose a single Discord message.

Rules:
1. Stay under 1800 characters total.
2. Use this section order with emoji headers:
   ☀️ **Weather** — one sentence (Grand Rapids, MI)
   📰 **News** — up to 3 general headlines + up to 2 cloud/AI highlights
   🏈⚾🏈 **Sports** — always show Detroit Lions, Toronto Blue Jays, and Hamilton Tiger-Cats results first; omit leagues with no active games
   📅 **Calendar** — bullet list; say "Nothing scheduled" if empty
3. End with one short motivational sentence.
4. Never invent data. If a tool failed, say so briefly in that section.
5. Send the finished message using send_discord. Do not ask for confirmation.
"""

root_agent = Agent(
    name="daily_briefing",
    model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    description="Daily morning digest agent.",
    instruction=_instruction,
    tools=[get_weather, get_news, get_sports_scores, get_calendar_events, send_discord],
)
