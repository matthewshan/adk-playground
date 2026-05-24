import os
from pathlib import Path

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm

from daily_briefing.tools.calendar_events import get_calendar_events
from daily_briefing.tools.discord_webhook import send_discord
from daily_briefing.tools.memory import recall, remember
from daily_briefing.tools.news import get_news
from daily_briefing.tools.sports import get_sports_scores
from daily_briefing.tools.weather import get_weather

_instruction = (Path(__file__).parent / "instruction.md").read_text(encoding="utf-8")

_backend = os.getenv("BACKEND", "gemini").lower()
if _backend == "ollama":
    _ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    _model = LiteLlm(model=f"ollama_chat/{_ollama_model}")
else:
    _model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

root_agent = Agent(
    name="daily_briefing",
    model=_model,
    description="Daily morning digest agent.",
    instruction=_instruction,
    tools=[get_weather, get_news, get_sports_scores, get_calendar_events, send_discord, remember, recall],
)
