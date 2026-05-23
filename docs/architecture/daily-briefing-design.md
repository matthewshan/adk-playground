# Architecture: Daily Briefing Agent

## Overview

A single-shot morning digest agent built on **Google ADK** and **Gemini 2.0 Flash**.
On each run it gathers weather, news, sports, and calendar data; asks Gemini to write
a friendly summary; and posts the result to Discord via webhook.

Intended deployment: a **Kubernetes CronJob** running daily at 7 AM.

---

## Module layout

```
daily_briefing/
  __init__.py           # package marker
  agent.py              # ADK Agent — wires model + tools
  instruction.md        # system prompt (edit without touching code)
  main.py               # InMemoryRunner entry point
  tools/
    __init__.py         # re-exports all five tool functions
    calendar_events.py  # Google Calendar v3 (service account)
    discord_webhook.py  # Discord incoming webhook delivery
    news.py             # GNews top headlines
    sports.py           # ESPN public API — team-centric scores
    weather.py          # Open-Meteo current + forecast
```

---

## Data flow

```
main.py (InMemoryRunner)
  └─ agent.py (ADK Agent — gemini-2.0-flash)
       ├─ tools/weather.py          → Open-Meteo API
       ├─ tools/news.py             → GNews API
       ├─ tools/sports.py           → ESPN public API
       ├─ tools/calendar_events.py  → Google Calendar API v3
       └─ tools/discord_webhook.py  → Discord webhook POST
```

---

## External APIs

| Tool module        | API                    | Auth                              | Notes                          |
|--------------------|------------------------|-----------------------------------|--------------------------------|
| `weather.py`       | Open-Meteo             | None                              | `current` + `hourly` params; `timezone=America/Detroit` |
| `news.py`          | GNews                  | `GNEWS_API_KEY`                   | 10 general headlines; 100 req/day free tier (localhost only) |
| `sports.py`        | ESPN public API        | None                              | `/teams`, `/teams/{id}`, `/teams/{id}/schedule`, `/scoreboard?dates=` |
| `calendar_events.py` | Google Calendar v3   | `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Service account; share calendar with SA email |
| `discord_webhook.py` | Discord webhook      | `DISCORD_WEBHOOK_URL`             | POST; truncates to 2000-char limit |

---

## Sports — tracked teams

Defined in `tools/sports.py` as `_TRACKED_TEAMS` (edit to add/remove teams):

```python
_TRACKED_TEAMS: list[tuple[str, str, str, str]] = [
    ("MLB", "baseball", "mlb",      "Toronto Blue Jays"),
    ("NFL", "football", "nfl",      "Detroit Lions"),
    ("CFL", "football", "cfl",      "Hamilton Tiger-Cats"),
]
```

Per team the tool returns: **record**, **recent completed games** (yesterday + today via scoreboard), and **upcoming games** (next 3 from team schedule). Off-season is detected when no recent games exist and the next game is >30 days away.

---

## Environment variables

See `daily_briefing/.env.example` for the full list. At runtime, `main.py` calls
`load_dotenv()` to load values from `daily_briefing/.env`.

---

## Key design decisions

- **Tool-per-API**: each `tools/*.py` file owns exactly one external API, making it easy to swap or disable a source without touching other tools.
- **Plain Python callables**: ADK picks up tools automatically — no decorators or schemas needed.
- **Single-shot execution**: `InMemoryRunner` runs the agent once and exits; no persistent session state.
- **System prompt in `instruction.md`**: editable without changing Python code.
- **Off-season detection**: sports tool suppresses score sections when a team is out of season and shows the next scheduled game date.

---

## Related docs

- [Plan](../plans/plan-daily-briefing-agent.md) — original feature plan and phase breakdown
- [API Setup Guide](../analysis/api-setup-guide.md) — how to obtain each API key
- [Google Calendar Private Setup](../analysis/google-calendar-private-setup.md) — Terraform workflow for service account
- [K8s Deployment Plan](../plans/plan-adk-k8s-deployment.md) — Phase 2 container + CronJob
