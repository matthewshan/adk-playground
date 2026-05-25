# Architecture: Daily Briefing Agent

## Overview

A single-shot morning digest agent built on **Google ADK** with a configurable
**Gemini** or **Ollama** backend. On each run it gathers weather, news, sports, and
calendar data through tool wrappers over raw API clients, asks the model to write a
friendly summary, and posts the result to Discord via webhook.

Intended deployment: a **Kubernetes CronJob** running daily at 7 AM.

---

## Module layout

```
daily_briefing/
  __init__.py           # package marker
  Dockerfile            # container image for the scheduled job
  agent.py              # ADK Agent — model selection, make_agent() factory, now_et() helper
  instruction.md        # system prompt (edit without touching code)
  main.py               # InMemoryRunner entry point
  apis/
    __init__.py         # package marker for raw API clients
    discord.py          # Discord webhook POST
    espn.py             # ESPN team, schedule, scoreboard, standings calls
    gnews.py            # GNews headlines
    google_calendar.py  # Google Calendar v3 client
    open_meteo.py       # Open-Meteo forecast client
    thesportsdb.py      # TheSportsDB fallback for CFL events
  tools/
    __init__.py         # re-exports tool functions for the agent
    calendar_events.py  # calendar formatting/orchestration
    discord_webhook.py  # delivery + Discord size guardrails
    news.py             # headline formatting/orchestration
    sports.py           # team-centric sports summary orchestration
    weather.py          # forecast formatting/orchestration
  smoke_tests/
    __init__.py         # package marker
    test_agent.py       # local runner that prints the digest instead of posting
    test_apis.py        # live smoke test for all tools
    test_sports.py      # sports unit tests + live smoke test
```

---

## Data flow

```
main.py / smoke_tests/test_agent.py
  └─ agent.py (ADK Agent)
       ├─ tools/weather.py          → apis/open_meteo.py      → Open-Meteo API
       ├─ tools/news.py             → apis/gnews.py           → GNews API
       ├─ tools/sports.py           → apis/espn.py            → ESPN public API
       │                              apis/thesportsdb.py     → TheSportsDB API (CFL fallback)
       ├─ tools/calendar_events.py  → apis/google_calendar.py → Google Calendar API v3
       └─ tools/discord_webhook.py  → apis/discord.py         → Discord webhook POST
```

---

## External APIs

| Tool module | Raw client | API | Auth | Notes |
|-------------|------------|-----|------|-------|
| `tools/weather.py` | `apis/open_meteo.py` | Open-Meteo | None | `current` + `hourly` params; `timezone=America/Detroit` |
| `tools/news.py` | `apis/gnews.py` | GNews | `GNEWS_API_KEY` | 10 general headlines; free tier is localhost-only |
| `tools/sports.py` | `apis/espn.py` | ESPN public API | None | Team lookup, records, schedule, scoreboard, standings |
| `tools/sports.py` | `apis/thesportsdb.py` | TheSportsDB | None | Fallback for CFL schedules/results when ESPN lacks current data |
| `tools/calendar_events.py` | `apis/google_calendar.py` | Google Calendar v3 | `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Service account; share calendar with the SA email |
| `tools/discord_webhook.py` | `apis/discord.py` | Discord webhook | `DISCORD_WEBHOOK_URL` | POST; caller truncates to the 2000-character limit |

---

## Sports tool behavior

`get_sports_scores()` always runs against the three default teams (Lions, Blue
Jays, Tiger-Cats) defined in `_DEFAULT_TEAMS`. The function accepts an optional
`teams` argument that smoke tests use to pass a custom list of `TrackedTeam`
objects:

```python
teams = [
  TrackedTeam("MLB", "baseball", "mlb", "Toronto Blue Jays"),
  TrackedTeam("NFL", "football", "nfl", "Detroit Lions"),
  TrackedTeam("CFL", "football", "cfl", "Hamilton Tiger-Cats"),
]
```

The `teams` parameter has **no type annotation** intentionally — annotating it
with `list[TrackedTeam] | None` generates a JSON Schema that the Gemini API
rejects, silently breaking tool calls. See
[adk-tool-design-lessons.md](adk-tool-design-lessons.md) §1–2.

The function guards against the LLM passing invalid values (e.g. a list of
strings) and falls back to `_DEFAULT_TEAMS` in that case.

Per team the tool returns a **record** when available, **recent completed games**,
**upcoming games** (next 3), and best-effort **standings**.

Sports lookup behavior is:

- ESPN is the primary source for team lookup, records, schedules, scoreboard checks, and standings.
- Same-day upcoming games are checked in scoreboard data so preseason games are not missed.
- If ESPN has no usable schedule or scoreboard data, the tool falls back to TheSportsDB.
- When the fallback is used, the W-L record is computed from completed season events.
- Off-season is detected when there are no recent games and the next game is more than 30 days away.

---

## Environment variables

See `daily_briefing/.env.example` for the full list. `main.py` loads
`daily_briefing/.env` before importing the agent so backend selection and keyed tool
configuration are available immediately. The smoke tests in `daily_briefing/smoke_tests/`
follow the same pattern.

---

## Key design decisions

- **Split raw clients from tool logic**: `apis/*.py` owns HTTP calls; `tools/*.py` owns formatting, orchestration, and ADK-facing function signatures.
- **Configurable model backend**: `BACKEND=gemini` uses `GEMINI_MODEL`; `BACKEND=ollama` wraps the local model through `LiteLlm`.
- **ESPN-first sports with fallback**: the sports tool uses ESPN when available and falls back to TheSportsDB for current CFL events.
- **Runnable smoke tests live beside the app**: `daily_briefing/smoke_tests/` contains live tool tests plus a local agent runner.
- **Agent factory for swappable output**: `agent.py` exposes `make_agent(output_tool, name)` so callers can substitute any output callable (e.g. a `print_briefing` stub in smoke tests) without duplicating model selection, instruction loading, or the tool list. `root_agent = make_agent()` is the production default; `test_agent.py` calls `make_agent(output_tool=print_briefing, name="daily_briefing_test")`. `now_et()` (Eastern-Time timestamp helper) is also exported from `agent.py` and shared by both runners.
- **Plain Python callables**: ADK picks up tools automatically — no decorators or schemas needed.
- **Single-shot execution**: `InMemoryRunner` runs the agent once and exits; no persistent session state.
- **System prompt in `instruction.md`**: editable without changing Python code.
- **Off-season detection**: sports output suppresses inactive leagues and shows the next scheduled game date when a team is out of season.
- **Avoid complex type annotations on tool parameters**: ADK's JSON schema generator turns dataclass/union types into `$defs`/`$ref` schemas that the Gemini API rejects. Use bare `param=None` (no annotation) and guard against invalid LLM-supplied values at the top of the function. See [adk-tool-design-lessons.md](adk-tool-design-lessons.md).

---

## Related docs

- [Plan](../plans/plan-daily-briefing-agent.md) — original feature plan and phase breakdown
- [API Setup Guide](../analysis/api-setup-guide.md) — how to obtain each API key
- [Google Calendar Private Setup](../analysis/google-calendar-private-setup.md) — external Terraform workflow for service account
- [K8s Deployment Plan](../plans/plan-adk-k8s-deployment.md) — Phase 2 container + CronJob
- [ADK Tool Design Lessons](adk-tool-design-lessons.md) — pitfalls and patterns for writing ADK tool functions
