# Copilot Instructions

This is a Python / Google ADK playground for experimenting with AI agents.
Follow these instructions when making changes to this repository.

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
    agent.py              # ADK Agent wiring
    instruction.md        # System prompt
    main.py               # Single-shot runner (InMemoryRunner)
    .env.example          # Required environment variables
    tools/
      __init__.py
      weather.py          # Open-Meteo
      news.py             # GNews
      sports.py           # ESPN public API
      calendar_events.py  # Google Calendar v3
      discord_webhook.py  # Discord webhook delivery
  docs/                   # See index above
  test_free_apis.py       # Smoke tests for no-key APIs (weather, sports)
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
