# CLAUDE.md — ADK Playground

This file is read automatically by Claude Code at session start.
It provides the same guidance as `.github/copilot-instructions.md` plus
Claude Code–specific commands and conventions.

---

## Project overview

A Python / Google ADK playground for experimenting with AI agents.

| Sub-project | Description |
|---|---|
| `minimal_ollama_adk/` | Tiny local ADK smoke test backed by Ollama |
| `daily_briefing/` | Morning digest agent — weather, news, sports, calendar → Discord |

---

## Common commands

### Install dependencies
```bash
python3 -m pip install --user -r requirements.txt
```

### Run the Discord bot (primary — handles both scheduled briefing and conversation)
```bash
# Copy and fill in the env file first
cp daily_briefing/.env.example daily_briefing/.env

# Requires DISCORD_BOT_TOKEN and DISCORD_BOT_CHANNEL_ID in daily_briefing/.env.
# Fires the morning digest automatically at 7 AM ET via discord.ext.tasks.
# See daily_briefing/.env.example for full setup instructions.
python3 -m daily_briefing.discord_bot
```

### Run the CLI debug runner (prints digest to stdout — no Discord required)
```bash
python3 -m daily_briefing.main
```

### Smoke tests (no agent, just tool calls)
```bash
# All tools (skips keyed APIs when env vars are absent)
python3 daily_briefing/smoke_tests/test_apis.py

# Sports-focused checks + unit assertions
python3 daily_briefing/smoke_tests/test_sports.py

# Full agent run — prints digest to stdout
python3 daily_briefing/smoke_tests/test_agent.py

# Discord bot unit tests — no token required
python3 daily_briefing/smoke_tests/test_discord_bot.py

# Supabase memory smoke test — requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY + GEMINI_API_KEY
python3 daily_briefing/smoke_tests/test_memory.py
```

### ADK web UI (dev/testing)
```bash
# Option A — run directly without Docker (fastest)
# Run from the repo root — ADK discovers daily_briefing/ automatically
adk web --host 0.0.0.0 --port 8000
# Then open http://localhost:8000 and select "daily_briefing"

# Option B — run in Docker
docker build -t daily-briefing-dev -f daily_briefing/Dockerfile.dev .
docker run --env-file daily_briefing/.env -p 8000:8000 daily-briefing-dev
# Then open http://localhost:8000
```

### Docker
```bash
# Discord bot image (primary long-running image — handles both scheduling and conversation)
docker build -t daily-briefing-bot -f daily_briefing/Dockerfile.bot .
docker run --env-file daily_briefing/.env daily-briefing-bot

# Dev / web UI image
docker build -t daily-briefing-dev -f daily_briefing/Dockerfile.dev .
docker run --env-file daily_briefing/.env -p 8000:8000 daily-briefing-dev
```

### Minimal Ollama smoke test
```bash
# Start Ollama (workspace-local install)
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS="$PWD/.ollama/models"
./.tools/ollama/bin/ollama serve &

# Run ADK example
export OLLAMA_API_BASE=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen2.5:0.5b
python3 -m minimal_ollama_adk.main "Reply with exactly: adk is working"
```

---

## Repository layout

```
adk-playground/
  minimal_ollama_adk/     # Minimal ADK example using a local Ollama model
  daily_briefing/         # Morning digest agent (primary project)
    agent.py              # ADK Agent — make_agent(), now_et(), _save_to_memory, LoadMemoryTool
    instruction.md        # System prompt (the ONLY place the prompt lives)
    main.py               # CLI debug runner — prints digest to stdout (not used in production)
    discord_bot.py        # Long-running bot — scheduled briefing (7 AM ET) + conversation
    Dockerfile            # Legacy CronJob image (bot now handles scheduling)
    Dockerfile.bot        # Container image for the Discord bot (primary)
    Dockerfile.dev        # Dev image — runs ADK web UI on port 8000
    .env.example          # Required environment variables — copy to .env
    apis/                 # Raw HTTP clients (one file per external service)
      discord.py          # Webhook client (not used by agent; kept for manual use)
      espn.py
      gnews.py
      google_calendar.py
      open_meteo.py
      supabase.py         # pgvector insert + similarity search
      thesportsdb.py
    memory/               # ADK memory service implementation
      supabase_memory_service.py
    tools/                # ADK-registered tool functions (one file per API)
      calendar_events.py
      discord_webhook.py  # Not used by agent; kept for manual use
      news.py
      sports.py
      weather.py
    smoke_tests/          # Runnable integration / unit tests
      test_agent.py
      test_apis.py
      test_discord_bot.py
      test_memory.py      # Supabase pgvector smoke test
      test_sports.py
  docs/                   # Architecture, setup, prompt, and deployment notes
  requirements.txt        # Shared Python dependencies
```

---

## Environment variables

All secrets live in `daily_briefing/.env` (never committed). Copy from
`daily_briefing/.env.example`.

| Variable | Required | Notes |
|---|---|---|
| `BACKEND` | no | `gemini` (default) or `ollama` |
| `GEMINI_API_KEY` | if Gemini | Google AI Studio key |
| `GEMINI_MODEL` | no | default `gemini-3.1-flash-lite` |
| `OLLAMA_API_BASE` | if Ollama | e.g. `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | if Ollama | e.g. `qwen2.5:7b` |
| `GNEWS_API_KEY` | yes | GNews free tier |
| `DISCORD_BOT_TOKEN` | yes | Discord bot token — Developer Portal → Bot → Token |
| `DISCORD_BOT_CHANNEL_ID` | yes | Channel ID the bot listens in |
| `GOOGLE_CALENDAR_ID` | yes | Calendar email address |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | yes | Base64-encoded service account JSON |
| `SUPABASE_URL` | optional | Supabase project URL — enables long-term memory |
| `SUPABASE_SERVICE_ROLE_KEY` | optional | Service-role key — bot warns and degrades if absent |

---

## Coding conventions

- **Python 3.11**, no type stubs required
- Tool functions are plain Python callables; ADK picks them up automatically
- One external API per file under `daily_briefing/apis/`
- One ADK tool per file under `daily_briefing/tools/`
- `load_dotenv()` is called in `main.py`; access secrets via `os.getenv()`
- Do **not** commit `.env`; use `.env.example` as the template
- Keep `instruction.md` as the only place the system prompt lives

---

## Documentation maintenance

**Keep docs in sync with the code.** When making a change that affects any of the
documents below, update the relevant file in the same commit — do not leave docs stale.

| If you change… | Update… |
|---|---|
| Module layout, APIs, or design decisions | `docs/architecture/daily-briefing-design.md` |
| New API keys or env vars | `daily_briefing/.env.example` and `docs/analysis/api-setup-guide.md` |
| Deployment or infrastructure | `docs/plans/plan-adk-k8s-deployment.md` |
| Prompt / context-engineering patterns | `docs/context-engineering.md` |
| `discord_bot.py` structure or bot behaviour | `docs/architecture/daily-briefing-design.md` |

---

## Docs index

```
docs/
  context-engineering.md               # Prompt-writing rules for small/local models
  architecture/
    daily-briefing-design.md           # Module layout, data flow, API table, design decisions
    adk-tool-design-lessons.md         # Lessons learned from ADK tool and memory design
  analysis/
    api-setup-guide.md                 # How to obtain each API key (GNews, Gemini, Discord, Calendar)
    discord-bot-setup.md               # Discord bot setup: Developer Portal, env vars, session design
    google-calendar-private-setup.md   # External Terraform workflow for Google Calendar service account
  integrations/
    supabase-vector-adk.md             # Supabase pgvector schema setup for ADK memory
  plans/
    plan-daily-briefing-agent.md       # Original feature plan and phase breakdown
    plan-adk-k8s-deployment.md         # Phase 2: container image + Kubernetes Deployment
```
