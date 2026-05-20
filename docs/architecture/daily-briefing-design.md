# Architecture: Daily Briefing Agent

## Overview

A single-shot morning digest agent built on **Google ADK**.
On each run it gathers weather, news, sports, and calendar data; asks the configured
model backend to write a summary; and posts the result to Discord via webhook.

Intended deployment: a **Kubernetes CronJob** running daily at 7 AM.

Model backend is selected by `BACKEND`:
- `gemini` (default): uses `GEMINI_MODEL` (default `gemini-3.5-flash`)
- `ollama`: uses `OLLAMA_MODEL` via ADK LiteLlm

---

## Module layout

```
daily_briefing/
  __init__.py           # package marker
  agent.py              # ADK Agent — wires backend + tools
  instruction.md        # system prompt (edit without touching code)
  main.py               # InMemoryRunner entry point
  test_apis.py          # smoke tests for tools
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
  └─ agent.py (ADK Agent)
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
| `weather.py`       | Open-Meteo             | None                              | current + hourly forecast |
| `news.py`          | GNews                  | `GNEWS_API_KEY`                   | top headlines |
| `sports.py`        | ESPN public API        | None                              | `/teams`, `/teams/{id}`, `/teams/{id}/schedule`, `/scoreboard?dates=` |
| `calendar_events.py` | Google Calendar v3   | `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Service account; share calendar with SA email |
| `discord_webhook.py` | Discord webhook      | `DISCORD_WEBHOOK_URL`             | POST; truncates to 2000-char limit |

---

## Sports — tracked teams

`get_sports_scores()` accepts a list of `TrackedTeam` entries.
The briefing prompt currently focuses on:
- Toronto Blue Jays (MLB)
- Detroit Lions (NFL)
- Hamilton Tiger-Cats (CFL)

Per team the tool returns: **record**, **recent completed games**, **upcoming games**, and (when available) **division standings**.

---

## Environment variables

See `daily_briefing/.env.example` for the full list. At runtime, `main.py` calls
`load_dotenv()` to load values from `daily_briefing/.env` before importing the agent.

---

## Key design decisions

- **Tool-per-API**: each `tools/*.py` file owns exactly one external API, making it easy to swap or disable a source without touching other tools.
- **Plain Python callables**: ADK picks up tools automatically — no decorators or schemas needed.
- **Single-shot execution**: `InMemoryRunner` runs the agent once and exits; no persistent session state.
- **System prompt in `instruction.md`**: editable without changing Python code.
- **Backend switch via env**: one agent supports either Gemini or local Ollama.

---

## Related docs

- [Plan](../plans/plan-daily-briefing-agent.md) — original feature plan and phase breakdown
- [API Setup Guide](../analysis/api-setup-guide.md) — how to obtain each API key
- [Google Calendar Private Setup](../analysis/google-calendar-private-setup.md) — Terraform workflow for service account
- [K8s Deployment Plan](../plans/plan-adk-k8s-deployment.md) — Phase 2 container + CronJob
