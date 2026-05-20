# ADK Playground

Python playground for experimenting with Google ADK agents.

## Projects

### 1) `daily_briefing` (primary)

A morning digest agent that gathers:
- Weather (Open-Meteo)
- Headlines (GNews)
- Sports updates (ESPN public API)
- Calendar events (Google Calendar service account)

It then writes a briefing and posts to Discord via webhook.

### 2) `minimal_ollama_adk`

A minimal local Ollama smoke-test agent for quick ADK wiring checks.

---

## Quickstart (daily briefing)

### 1. Install dependencies

```bash
python3 -m pip install --user -r requirements.txt
```

### 2. Configure environment

```bash
cp daily_briefing/.env.example daily_briefing/.env
```

Fill in required values in `daily_briefing/.env`:
- `BACKEND=gemini` or `BACKEND=ollama`
- `GEMINI_API_KEY` (for Gemini backend)
- `GNEWS_API_KEY`
- `DISCORD_WEBHOOK_URL`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`

### 3. Run once

```bash
python3 -m daily_briefing.main
```

---

## Smoke tests

Run tool-level checks:

```bash
python3 daily_briefing/test_apis.py
```

Notes:
- Network-restricted environments may fail weather/sports API checks.
- Keyed checks are skipped when related env vars are not set.

---

## Docs

- Architecture: `docs/architecture/daily-briefing-design.md`
- API/key setup: `docs/analysis/api-setup-guide.md`
- Google Calendar private setup: `docs/analysis/google-calendar-private-setup.md`
- Deployment plan: `docs/plans/plan-adk-k8s-deployment.md`
- Context engineering notes: `docs/context-engineering.md`
