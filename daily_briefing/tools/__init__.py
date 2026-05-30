"""Tool functions for the daily briefing agent.

Each tool handles one domain. Raw API calls live in daily_briefing/apis/:
  apis/open_meteo.py      — Open-Meteo (no key required)
  apis/gnews.py           — GNews (key required)
  apis/espn.py            — ESPN public API (no key required)
  apis/thesportsdb.py     — TheSportsDB (no key required)
  apis/google_calendar.py — Google Calendar v3 via service account
  apis/discord.py         — Discord incoming webhook
  apis/tavily.py          — Tavily web search (key required; non-Gemini backends)
"""

from daily_briefing.tools.calendar_events import get_calendar_events
from daily_briefing.tools.discord_webhook import send_discord
from daily_briefing.tools.news import get_news
from daily_briefing.tools.sports import TrackedTeam, get_sports_scores
from daily_briefing.tools.weather import get_weather
from daily_briefing.tools.web_search import web_search

__all__ = [
    "get_calendar_events",
    "get_news",
    "get_sports_scores",
    "get_weather",
    "send_discord",
    "web_search",
    "TrackedTeam",
]
