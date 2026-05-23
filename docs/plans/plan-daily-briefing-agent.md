# Plan: Daily Briefing ADK Agent

This document captures the original build plan for the daily briefing agent. The current
implementation lives under `daily_briefing/` and the architecture source of truth is
`docs/architecture/daily-briefing-design.md`.

The implemented app fetches weather for Grand Rapids MI, breaking news (including cloud
and AI), sports updates for Detroit Lions, Toronto Blue Jays, and Hamilton Tiger-Cats,
and Google Calendar events, uses Gemini Flash or Ollama to write a friendly summary,
and delivers it to Discord on a schedule.

---

## What the app does

```
Run once daily at 7 AM
- Fetch weather         → Open-Meteo (no key)
- Fetch top news        → GNews
- Fetch sports scores   → ESPN public API + TheSportsDB fallback for CFL
- Fetch calendar events → Google Calendar API v3 via service account
- Summarize all four    → Gemini 3.5 Flash or Ollama
- Post to Discord       → Webhook POST
```

The entry point (`main.py`) runs the ADK agent with a single prompt. The agent decides which tools to call, collects the results, writes the digest, and calls `send_discord`. No interactive loop; the process exits when done.

---

## Module layout

```
daily_briefing/
- __init__.py
- agent.py
- apis/            ← raw HTTP clients
- instruction.md
- main.py
- smoke_tests/     ← runnable smoke tests and local agent runner
- tools/           ← ADK-facing tool functions and orchestration
```

---

## Tech stack

| Concern | Choice |
|---|---|
| LLM | `gemini-3.5-flash` by default, or a local Ollama model via `LiteLlm` |
| Weather | Open-Meteo — free, no key |
| News | GNews — key required |
| Sports | ESPN public API plus TheSportsDB fallback for current CFL schedule gaps |
| Calendar | Google Calendar API v3 via service account |
| Delivery | Discord webhook |
| Schedule | k8s CronJob (details below) |
| Image | `ghcr.io/matthewshan/daily-briefing` via GitHub Actions |

---

## Phase 1 — Data tools

Build the raw API clients under `daily_briefing/apis/` first, then keep formatting and
agent-facing logic in `daily_briefing/tools/`. Each exported tool remains a plain Python
callable that returns a string, so ADK can discover it without extra schemas.

**Current tool modules:**

`tools/weather.py`
- Open-Meteo endpoint; default coords Grand Rapids, MI (42.96, -85.67)
- Returns a one-line string: `"72°F, clear sky, wind 8 mph"`
- No API key

`tools/news.py`
- GNews top headlines, English
- Includes general headlines plus cloud/AI coverage in the formatted result
- Returns a bulleted list of headline + source
- Requires `GNEWS_API_KEY` from env

`tools/sports.py`
- ESPN team lookup, records, schedules, same-day scoreboard checks, and standings
- TheSportsDB fallback when ESPN does not have current CFL schedule data
- Favourite teams to highlight: **Detroit Lions** (NFL), **Toronto Blue Jays** (MLB), **Hamilton Tiger-Cats** (CFL)
- Returns recent results, upcoming games, and off-season messaging per tracked team
- No API key

`tools/calendar_events.py`
- Google Calendar API v3, events for today
- Auth: service account JSON for private calendars
- Requires `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` and `GOOGLE_CALENDAR_ID` from env
- Returns a bulleted list of event titles + times, or `"Nothing scheduled"`

`tools/discord_webhook.py`
- `POST` to `DISCORD_WEBHOOK_URL` from env
- Returns `"Sent"` on success; raises on HTTP error so the agent reports the failure

**Private Google Calendar note:** the current implementation uses a service account only.
Create the service account in Google Cloud, share the calendar with the service account
email (view-only), base64-encode the JSON key, and pass it via
`GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`.

**Smoke tests:**

- `python daily_briefing/smoke_tests/test_apis.py` exercises all tools with live API calls.
- `python daily_briefing/smoke_tests/test_sports.py` runs sports unit tests, then a live sports smoke test.
- `python daily_briefing/smoke_tests/test_agent.py` runs the agent and prints the digest instead of posting to Discord.

---

## Phase 2 — ADK agent

**`instruction.md`** — the agent's personality and output contract. Lives in a separate file so it can be tuned without rebuilding the image.

```markdown
You are a friendly personal assistant delivering a daily morning briefing for someone in Grand Rapids, MI.

Call each tool to collect the data, then compose a single Discord message.

Rules:
1. Stay under 1800 characters total.
2. Use this section order with emoji headers:
    - ☀️ **Weather** — one sentence (Grand Rapids, MI)
    - 📰 **News** — up to 3 general headlines + up to 2 cloud/AI highlights
    - 🏈⚾🏈 **Sports** — always show Detroit Lions, Toronto Blue Jays, and Hamilton Tiger-Cats results first; omit leagues with no active games
    - 📅 **Calendar** — bullet list; say "Nothing scheduled" if empty
3. End with one short motivational sentence.
4. Never invent data. If a tool failed, say so briefly in that section.
5. Send the finished message using send_discord. Do not ask for confirmation.
```

**`agent.py`** — wires the tools and model together:

```python
import os
from pathlib import Path
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from daily_briefing.tools import (
    get_weather, get_news, get_sports_scores,
    get_calendar_events, send_discord,
)

instruction = (Path("daily_briefing") / "instruction.md").read_text(encoding="utf-8")

backend = os.getenv("BACKEND", "gemini").lower()
if backend == "ollama":
    model = LiteLlm(model=f"ollama_chat/{os.getenv('OLLAMA_MODEL', 'qwen2.5:7b')}")
else:
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

root_agent = Agent(
    name="daily_briefing",
    model=model,
    description="Daily morning digest agent.",
    instruction=instruction,
    tools=[get_weather, get_news, get_sports_scores, get_calendar_events, send_discord],
)
```

**`main.py`** — single-shot runner, no web server, no interactive loop:

```python
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types
from daily_briefing.agent import root_agent

async def run():
    load_dotenv(Path("daily_briefing") / ".env")
    runner = InMemoryRunner(agent=root_agent, app_name="daily_briefing")
    session = await runner.session_service.create_session(
        app_name="daily_briefing", user_id="scheduler"
    )
    async for event in runner.run_async(
        user_id="scheduler",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(
                "Fetch weather for Grand Rapids MI, top news plus the latest cloud and AI news, "
                "NFL/MLB/CFL scores (highlight Detroit Lions, Toronto Blue Jays, Hamilton Tiger-Cats), "
                "and today's calendar events. Write and send the morning digest."
            )],
        ),
    ):
        if event.content:
            for part in (event.content.parts or []):
                if part.text:
                    print(part.text)

if __name__ == "__main__":
    asyncio.run(run())
```

**End-to-end local test:**
```bash
cp daily_briefing/.env.example daily_briefing/.env  # fill in keys
python -m daily_briefing.main
# expect a Discord message to arrive
```

---

## Phase 3 — Prompt iteration

Once the agent is working end-to-end, `instruction.md` is the only thing to tune. Common adjustments:

- Change the tone ("professional" vs "casual")
- Add or remove a section (e.g. add a stock ticker or a "word of the day")
- Tighten the character limit if Discord messages feel long
- Add a "top story" section that picks the single most important headline

Each edit is a text change with no Python to modify and no container rebuild needed locally. Only rebuild when deploying to k8s.

---

## Phase 4 — Container and CI/CD

**`Dockerfile`** — non-root, minimal image:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN useradd -m -u 1000 agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY daily_briefing/ daily_briefing/
USER agent
CMD ["python", "-m", "daily_briefing.main"]
```

**`requirements.txt` additions:**
```
requests
google-auth
google-api-python-client
```

**GitHub Actions (`.github/workflows/docker-publish.yml`):**
- Triggers on push to `main` touching `daily_briefing/**` or `Dockerfile`
- Builds and pushes `ghcr.io/matthewshan/daily-briefing:latest` + `:<sha>` using `GITHUB_TOKEN`

**Local container test before pushing:**
```bash
docker build -t daily-briefing .
docker run --env-file daily_briefing/.env daily-briefing
```

---

## Phase 5 — k8s deployment (high-level)

Standard service pattern in `k3s-homelab/services/daily-briefing/` — same structure as `services/n8n/`:

- `ns.yaml` — namespace
- `external-secret.yaml` — maps 5 Infisical keys into `briefing-secrets`; sync wave `-1`
- `cronjob.yaml` — `schedule: "0 7 * * *"`, `timeZone: "America/Detroit"`, `envFrom: briefing-secrets`, `restartPolicy: OnFailure`
- `kustomization.yaml` — references the three above

**Environment values to provision before first sync:**

| Key | Source |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio |
| `GNEWS_API_KEY` | GNews account |
| `DISCORD_WEBHOOK_URL` | Discord → Server Settings → Integrations → Webhooks |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Terraform output from the Google Calendar setup |
| `GOOGLE_CALENDAR_ID` | Google Calendar → Calendar Settings → Calendar ID |

The existing ApplicationSet in `services-appset.yaml` autodiscovers `services/daily-briefing/` — no changes needed there.

**Manual trigger to verify before waiting for 7 AM:**
```bash
kubectl create job --from=cronjob/daily-briefing manual-test -n daily-briefing
kubectl logs -f job/manual-test -n daily-briefing
```

---

## Future directions

| Idea | What to change |
|---|---|
| Add a stock price | Add a raw client under `daily_briefing/apis/`, a new tool module under `daily_briefing/tools/`, and a new line in `instruction.md` |
| SMS instead of / in addition to Discord | Swap or add a `send_sms()` tool (Twilio free trial) |
| Route through n8n | Replace `send_discord()` with a POST to an n8n webhook; n8n handles multi-channel fan-out |
| Try a local LLM | Change `GEMINI_MODEL` env var to an Ollama model string; use `LiteLlm` wrapper as in `minimal_ollama_adk` |
| Weekly digest variant | Duplicate the agent with a different schedule and a `instruction_weekly.md` that asks for a 7-day summary |

---

## Later: memory and two-way Discord

Two natural next steps once the one-way digest is solid:

**Memory** — right now every run is stateless. Adding ADK persistent memory (e.g. `VertexAiMemoryBankService` or a simple file/database store) would let the agent remember things across days: which news stories it has already mentioned, personal preferences ("I don't care about baseball in February"), or a running log of what the weather has been like. This is a pure `agent.py` + runner change; the tools and k8s manifests stay the same.

**Reading and responding to Discord** — today the agent only posts. A future version could poll a Discord channel (or receive events via a Discord bot + webhook listener) so you can reply to the morning digest and have the agent respond. This would change the deployment from a one-shot CronJob to a long-running bot process, and would require a Discord bot token instead of (or alongside) the webhook URL. The ADK agent and tools layer would stay largely the same — only the delivery and runner model changes.
