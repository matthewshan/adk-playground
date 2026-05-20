"""Tool functions for the daily briefing agent.

Each sub-module owns one external API:
  weather          — Open-Meteo (no key required)
  news             — GNews (key required)
  sports           — ESPN public API (no key required)
  calendar_events  — Google Calendar v3 via service account
  discord_webhook  — Discord incoming webhook
"""

from daily_briefing.tools.calendar_events import get_calendar_events
from daily_briefing.tools.discord_webhook import send_discord
from daily_briefing.tools.news import get_news
from daily_briefing.tools.sports import TrackedTeam, get_sports_scores
from daily_briefing.tools.weather import get_weather

__all__ = [
    "get_calendar_events",
    "get_news",
    "get_sports_scores",
    "get_weather",
    "send_discord",
    "TrackedTeam",
]
