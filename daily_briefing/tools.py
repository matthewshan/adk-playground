"""Tool functions for the daily briefing ADK agent.

Each function is a plain Python callable that ADK picks up automatically.
Functions are grouped by data source:
  - get_weather      — Open-Meteo (no key required)
  - get_news         — NewsAPI.org (NEWS_API_KEY)
  - get_sports_scores — ESPN public scoreboard (no key required)
  - get_calendar_events — Google Calendar v3 via service account
  - send_discord     — Discord incoming webhook (DISCORD_WEBHOOK_URL)
"""

from __future__ import annotations

import base64
import datetime
import json
import os

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build


# ── WMO weather-code descriptions (Open-Meteo) ────────────────────────────────

_WMO_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight showers",
    81: "moderate showers",
    82: "violent showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


# ── Weather ────────────────────────────────────────────────────────────────────


def get_weather(
    latitude: float = 42.96,
    longitude: float = -85.67,
) -> str:
    """Fetch current weather for the given coordinates using Open-Meteo (no key required).

    Args:
        latitude: Latitude of the location. Default is Grand Rapids, MI.
        longitude: Longitude of the location. Default is Grand Rapids, MI.

    Returns:
        A one-line string such as "72°F, clear sky, wind 8 mph".
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weathercode,windspeed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "America/Detroit",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    current = resp.json()["current"]

    temp = round(current["temperature_2m"])
    code = int(current["weathercode"])
    wind = round(current["windspeed_10m"])
    condition = _WMO_CODES.get(code, f"code {code}")
    return f"{temp}°F, {condition}, wind {wind} mph"


# ── News ───────────────────────────────────────────────────────────────────────


def get_news() -> str:
    """Fetch top general headlines plus cloud and AI highlights from NewsAPI.

    Requires the NEWS_API_KEY environment variable.

    Returns:
        A bulleted string listing headline and source.
    """
    api_key = os.environ["NEWS_API_KEY"]
    base_url = "https://newsapi.org/v2/top-headlines"

    def _fetch(params: dict) -> list[dict]:
        r = requests.get(
            base_url, params={"apiKey": api_key, **params}, timeout=10
        )
        r.raise_for_status()
        return r.json().get("articles", [])

    general = _fetch({"language": "en", "pageSize": 5})
    cloud = _fetch({"q": "cloud computing", "language": "en", "pageSize": 3})
    ai_articles = _fetch({"q": "artificial intelligence", "language": "en", "pageSize": 3})

    seen: set[str] = set()
    lines: list[str] = []

    def _add(articles: list[dict], tag: str = "") -> None:
        for a in articles:
            title = (a.get("title") or "").strip()
            if not title or title == "[Removed]":
                continue
            source = (a.get("source") or {}).get("name", "")
            key = title.lower()
            if key not in seen:
                seen.add(key)
                suffix = f" [{tag}]" if tag else ""
                lines.append(f"• {title} — {source}{suffix}")

    _add(general)
    _add(cloud, "Cloud")
    _add(ai_articles, "AI")

    return "\n".join(lines) if lines else "No news available."


# ── Sports ─────────────────────────────────────────────────────────────────────

_ESPN_LEAGUES: list[tuple[str, str, str, str]] = [
    ("NFL", "football", "nfl", "Detroit Lions"),
    ("MLB", "baseball", "mlb", "Toronto Blue Jays"),
    ("CFL", "football", "cfl", "Hamilton"),  # matches "Hamilton Tiger-Cats"
]


def get_sports_scores() -> str:
    """Fetch current scoreboard data from the public ESPN API (no key required).

    Highlights Detroit Lions (NFL), Toronto Blue Jays (MLB), and Hamilton
    Tiger-Cats (CFL). Favourite-team games are listed first within each league.

    Returns:
        Formatted scores per league, or "No games (off-season)" if empty.
    """
    sections: list[str] = []

    for league_label, sport, league, favourite in _ESPN_LEAGUES:
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports"
            f"/{sport}/{league}/scoreboard"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            events: list[dict] = resp.json().get("events", [])
        except requests.RequestException as exc:
            sections.append(f"**{league_label}**: error fetching scores ({exc})")
            continue

        if not events:
            sections.append(f"**{league_label}**: No games (off-season)")
            continue

        fav_lines: list[str] = []
        other_lines: list[str] = []

        for event in events:
            name: str = event.get("name", "")
            competitions: list[dict] = event.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            competitors: list[dict] = comp.get("competitors", [])
            status_desc: str = (
                (event.get("status") or {})
                .get("type", {})
                .get("description", "")
            )

            score_parts: list[str] = []
            for c in competitors:
                team_name = (c.get("team") or {}).get("displayName", "")
                score = c.get("score", "")
                score_parts.append(f"{team_name} {score}".strip())

            score_str = " vs ".join(score_parts) if score_parts else name
            line = f"  • {score_str} ({status_desc})"

            if favourite.lower() in name.lower():
                fav_lines.append(line)
            else:
                other_lines.append(line)

        ordered = fav_lines + other_lines
        sections.append(f"**{league_label}**:\n" + "\n".join(ordered))

    return "\n\n".join(sections) if sections else "No sports data available."


# ── Calendar ───────────────────────────────────────────────────────────────────

_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_events() -> str:
    """Fetch today's events from a private Google Calendar via service account.

    Required environment variables:
      GOOGLE_CALENDAR_ID                   — Calendar ID (full address or "primary")
      GOOGLE_SERVICE_ACCOUNT_JSON_BASE64   — base64-encoded service account JSON key

    Returns:
        A bulleted list of event titles and times, or "Nothing scheduled".
    """
    sa_b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "")
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    if not sa_b64:
        return "Calendar unavailable: GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 not set."

    sa_info = json.loads(base64.b64decode(sa_b64).decode("utf-8"))
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=_CALENDAR_SCOPES
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.datetime.now(datetime.timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + datetime.timedelta(days=1)

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    items: list[dict] = result.get("items", [])
    if not items:
        return "Nothing scheduled"

    lines: list[str] = []
    for event in items:
        summary = event.get("summary", "(no title)")
        start = event.get("start", {})
        if "dateTime" in start:
            dt = datetime.datetime.fromisoformat(start["dateTime"])
            # Cross-platform 12-hour time without leading zero
            hour = dt.hour % 12 or 12
            time_str = f"{hour}:{dt.strftime('%M %p')}"
        else:
            time_str = "all day"
        lines.append(f"• {summary} @ {time_str}")

    return "\n".join(lines)


# ── Discord ────────────────────────────────────────────────────────────────────


def send_discord(message: str) -> str:
    """Post a message to a Discord channel via incoming webhook.

    Requires the DISCORD_WEBHOOK_URL environment variable.

    Args:
        message: The formatted briefing text to post.

    Returns:
        "Sent" on success. Raises requests.HTTPError on failure.
    """
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    # Discord's per-message limit is 2000 characters.
    payload = {"content": message[:2000]}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
    return "Sent"
