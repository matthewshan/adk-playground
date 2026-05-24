# Copilot Instructions

This is a Python / Google ADK playground for experimenting with AI agents.
Follow these instructions when making changes to this repository.

> **Dual-assistant repo:** This file is read by GitHub Copilot.
> The equivalent file for Claude Code is [`CLAUDE.md`](../CLAUDE.md) at the
> repo root. Keep the two files in sync when updating project guidance.

---

## Documentation maintenance

**Keep docs in sync with the code.** When you make a change that affects any of the
documents listed below, update the relevant file in the same response — do not leave
docs stale. Specifically:

- If the module layout, APIs, or design decisions change → update `docs/architecture/daily-briefing-design.md`
- If new API keys or env vars are added → update `daily_briefing/.env.example` and `docs/analysis/api-setup-guide.md`
- If the deployment or infrastructure changes → update `docs/plans/plan-adk-k8s-deployment.md`
- If prompt / context-engineering patterns change → update `docs/context-engineering.md`

---

## Docs index

```
docs/
  context-engineering.md               # Prompt-writing rules for small/local models
  architecture/
    daily-briefing-design.md           # Module layout, data flow, API table, design decisions
  analysis/
    api-setup-guide.md                 # How to obtain each API key (GNews, Gemini, Discord, Calendar)
    google-calendar-private-setup.md   # External Terraform workflow for Google Calendar service account
  plans/
    plan-daily-briefing-agent.md       # Original feature plan and phase breakdown
    plan-adk-k8s-deployment.md         # Phase 2: container image + Kubernetes CronJob
```

---

## Project structure

```
adk-playground/
  minimal_ollama_adk/     # Minimal ADK example using a local Ollama model
  daily_briefing/         # Morning digest agent (primary project)
    agent.py              # ADK Agent wiring — model selection + tool registration
    instruction.md        # System prompt (the ONLY place the prompt lives)
    main.py               # Single-shot runner (InMemoryRunner)
    .env.example          # Required environment variables — copy to .env
    apis/                 # Raw HTTP clients (one file per external service)
      discord.py
      espn.py
      gnews.py
      google_calendar.py
      open_meteo.py
      thesportsdb.py
    tools/                # ADK-registered tool functions (one file per API)
      weather.py          # Open-Meteo
      news.py             # GNews
      sports.py           # ESPN + TheSportsDB
      calendar_events.py  # Google Calendar v3
      discord_webhook.py  # Discord webhook delivery
    smoke_tests/          # Runnable integration / unit tests
      test_agent.py
      test_apis.py
      test_sports.py
  docs/                   # See index above
  requirements.txt
```

---

## Coding conventions

- **Python 3.11**, no type stubs required
- Tool functions are plain Python callables; ADK picks them up automatically
- One external API per file under `daily_briefing/tools/`
- `load_dotenv()` is called in `main.py`; access secrets via `os.getenv()`
- Do not commit `.env`; use `.env.example` as the template
- Keep `instruction.md` as the only place the system prompt lives
