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
  Dockerfile            # container image for the scheduled CronJob (legacy — bot now handles scheduling)
  Dockerfile.bot        # container image for the long-running Discord bot
  Dockerfile.dev        # dev image — runs ADK web UI on port 8000 (adk web)
  agent.py              # ADK Agent — wires model + tools; make_agent(), now_et(), _save_to_memory
  instruction.md        # system prompt (edit without touching code)
  main.py               # CLI debug runner — prints digest to stdout (not used in production)
  discord_bot.py        # long-running Discord bot: scheduled briefing + conversational messages
  apis/
    __init__.py         # package marker for raw API clients
    discord.py          # Discord webhook POST (unused by agent; kept for manual use)
    espn.py             # ESPN team, schedule, scoreboard, standings calls
    gnews.py            # GNews headlines
    google_calendar.py  # Google Calendar v3 client
    open_meteo.py       # Open-Meteo forecast client
    supabase.py         # Supabase pgvector insert + similarity search
    thesportsdb.py      # TheSportsDB fallback for CFL events
  memory/
    __init__.py         # package marker
    supabase_memory_service.py  # ADK BaseMemoryService backed by Supabase pgvector
  tools/
    __init__.py         # re-exports tool functions for the agent
    calendar_events.py  # calendar formatting/orchestration
    discord_webhook.py  # delivery + Discord size guardrails (unused by agent; kept for manual use)
    news.py             # headline formatting/orchestration
    sports.py           # team-centric sports summary orchestration
    weather.py          # forecast formatting/orchestration
  smoke_tests/
    __init__.py         # package marker
    test_agent.py       # local runner that prints the digest to stdout
    test_apis.py        # live smoke test for all tools
    test_discord_bot.py # unit tests for discord_bot helpers (no token required)
    test_memory.py      # Supabase pgvector smoke test (embed → insert → similarity search)
    test_sports.py      # sports unit tests + live smoke test
```

---

## Data flow

The Discord bot is the single process that owns all agent interactions.
There is no separate CronJob; scheduling is handled internally by `discord.ext.tasks`.

### Scheduled briefing (daily at 7 AM ET)

```
discord_bot.py — @tasks.loop(time=07:00 ET)
  └─ _run_agent("scheduler", briefing_prompt)
       └─ Runner (Runner + SupabaseMemoryService)
            └─ agent.py (ADK Agent)
                 ├─ tools/weather.py          → apis/open_meteo.py      → Open-Meteo API
                 ├─ tools/news.py             → apis/gnews.py           → GNews API
                 ├─ tools/sports.py           → apis/espn.py            → ESPN public API
                 │                              apis/thesportsdb.py     → TheSportsDB API (CFL fallback)
                 ├─ tools/calendar_events.py  → apis/google_calendar.py → Google Calendar API v3
                 └─ LoadMemoryTool()          → SupabaseMemoryService.search_memory()
            └─ after_agent_callback (_save_to_memory)
                 └─ SupabaseMemoryService.add_session_to_memory()
                      └─ apis/supabase.py → Supabase pgvector (agent_memory table)
  └─ channel.send() [chunked, ≤2000 chars per send]
```

### Conversational messages

```
discord_bot.py — on_message (all messages in DISCORD_BOT_CHANNEL_ID)
  ├─ per-user asyncio.Lock  (serialises rapid messages from same user)
  ├─ _get_or_create_session(user_id) → Runner.session_service (InMemorySessionService)
  └─ _run_agent(user_id, prompt)     → Runner.run_async()
       └─ agent.py (same tools as scheduled briefing; LoadMemoryTool recalls past sessions)
  └─ message.channel.send() [chunked, ≤2000 chars per send]
```

Both paths use the same `Runner` instance initialised in `main()` — same agent, same
memory service, same model config.  Memory is scoped per user_id so per-user sessions
are isolated from each other and from the `"scheduler"` scope.

### Local debug runner (`main.py`)

```
main.py (CLI only — not used in production)
  └─ Runner + SupabaseMemoryService
       └─ agent.py → same tools → prints digest to stdout
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
| `discord_bot.py` | discord.py Gateway | Discord bot | `DISCORD_BOT_TOKEN` | Inbound messages → ADK agent → `channel.send()` |

---

## Sports tool behavior

`get_sports_scores()` accepts a list of `TrackedTeam` objects from the caller. The smoke
tests use the following set:

```python
teams = [
  TrackedTeam("MLB", "baseball", "mlb", "Toronto Blue Jays"),
  TrackedTeam("NFL", "football", "nfl", "Detroit Lions"),
  TrackedTeam("CFL", "football", "cfl", "Hamilton Tiger-Cats"),
]
```

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

- **Bot is the single process for all agent interactions**: `discord_bot.py` handles both the scheduled morning briefing (via `discord.ext.tasks`) and conversational messages. No separate CronJob process is needed — one Deployment, one Dockerfile, one Runner.
- **Agent never calls send_discord**: delivery is always handled by the bot via `channel.send()`. The agent composes text and returns it; the bot chunks and posts it. `tools/discord_webhook.py` and `apis/discord.py` are retained for manual use but are not registered as agent tools.
- **Supabase long-term memory via pgvector**: `SupabaseMemoryService` (implementing ADK's `BaseMemoryService`) embeds agent output turns and stores them in Supabase. The agent exposes `LoadMemoryTool()` for on-demand semantic recall. If Supabase env vars are absent, the bot logs a startup warning and continues without memory.
- **Per-user memory isolation**: each Discord user_id maps to a distinct `app_name/user_id` scope in Supabase. The scheduled briefing uses `user_id="scheduler"` — isolated from per-user scopes.
- **Split raw clients from tool logic**: `apis/*.py` owns HTTP calls; `tools/*.py` owns formatting, orchestration, and ADK-facing function signatures.
- **Configurable model backend**: `BACKEND=gemini` uses `GEMINI_MODEL`; `BACKEND=ollama` wraps the local model through `LiteLlm`.
- **ESPN-first sports with fallback**: the sports tool uses ESPN when available and falls back to TheSportsDB for current CFL events.
- **Runnable smoke tests live beside the app**: `daily_briefing/smoke_tests/` contains live tool tests, a local agent runner, and a Supabase memory smoke test.
- **Plain Python callables**: ADK picks up tools automatically — no decorators or schemas needed.
- **System prompt in `instruction.md`**: editable without changing Python code.
- **Off-season detection**: sports output suppresses inactive leagues and shows the next scheduled game date when a team is out of season.

---

## Related docs

- [Plan](../plans/plan-daily-briefing-agent.md) — original feature plan and phase breakdown
- [API Setup Guide](../analysis/api-setup-guide.md) — how to obtain each API key
- [Google Calendar Private Setup](../analysis/google-calendar-private-setup.md) — external Terraform workflow for service account
- [K8s Deployment Plan](../plans/plan-adk-k8s-deployment.md) — Phase 2 container + CronJob
