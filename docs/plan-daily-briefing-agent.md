# Plan: Daily Briefing ADK Agent

A morning digest agent that fetches weather, breaking news, sports scores (NFL, MLB, CFL), and Google Calendar events, uses Gemini Flash to write a friendly summary, and delivers it to Discord — triggered every morning by a k8s CronJob.

---

## What the app does

```
Run once daily at 7 AM
  ├─ Fetch weather         → Open-Meteo (no key)
  ├─ Fetch top news        → NewsAPI free tier
  ├─ Fetch sports scores   → ESPN public scoreboard API (no key)
  ├─ Fetch calendar events → Google Calendar API
  ├─ Summarize all four    → Gemini 2.0 Flash (free tier)
  └─ Post to Discord       → Webhook POST
```

The entry point (`main.py`) runs the ADK agent with a single prompt. The agent decides which tools to call, collects the results, writes the digest, and calls `send_discord`. No interactive loop; the process exits when done.

---

## Module layout

```
daily_briefing/
  __init__.py
  instruction.md   ← system prompt (edit without touching code)
  tools.py         ← one function per data source
  agent.py         ← ADK Agent wiring tools + model
  main.py          ← single-shot runner
```

---

## Tech stack

| Concern | Choice |
|---|---|
| LLM | `gemini-2.0-flash` via [Google AI Studio](https://aistudio.google.com/app/apikey) free API key |
| Weather | Open-Meteo — free, no key |
| News | NewsAPI.org developer tier — free, 100 req/day |
| Sports | ESPN public scoreboard API — free, no key; covers NFL, MLB, CFL |
| Calendar | Google Calendar API v3 |
| Delivery | Discord webhook |
| Schedule | k8s CronJob (details below) |
| Image | `ghcr.io/matthewshan/daily-briefing` via GitHub Actions |

---

## Phase 1 — Data tools

Build and test each tool function in isolation before wiring up the agent. Each function is a plain Python function that takes typed arguments and returns a string. ADK picks them up automatically.

**`tools.py` functions:**

`get_weather(latitude: float, longitude: float) -> str`
- Open-Meteo endpoint; default coords Wyoming, MI (42.70, -85.76)
- Returns a one-line string: `"72°F, clear sky, wind 8 mph"`
- No API key

`get_news() -> str`
- NewsAPI top headlines, English, top 5
- Returns a bulleted list of headline + source
- Requires `NEWS_API_KEY` from env

`get_sports_scores() -> str`
- ESPN scoreboard endpoints for NFL, MLB, CFL
  - `site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`
  - `site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard`
  - `site.api.espn.com/apis/site/v2/sports/football/cfl/scoreboard`
- Returns final scores per league, or `"No games (off-season)"` if scoreboard is empty
- No API key

`get_calendar_events() -> str`
- Google Calendar API v3, events for today
- Auth: API key for public calendars; service account JSON for private (see note below)
- Requires `GOOGLE_CALENDAR_API_KEY` and `GOOGLE_CALENDAR_ID` from env
- Returns a bulleted list of event titles + times, or `"Nothing scheduled"`

`send_discord(message: str) -> str`
- `POST` to `DISCORD_WEBHOOK_URL` from env
- Returns `"Sent"` on success; raises on HTTP error so the agent reports the failure

**Private Google Calendar note:** API keys only work for public calendars. For a private calendar, create a service account in Google Cloud Console, share the calendar with the service account email (view-only), download the JSON key, base64-encode it, and store it in Infisical as `google-calendar-service-account-json`. Update `tools.py` to decode and load it via `google.oauth2.service_account.Credentials`.

**Smoke test for each tool:**
```python
# run standalone before wiring to ADK
from daily_briefing.tools import get_weather, get_news, get_sports_scores, get_calendar_events
print(get_weather(42.70, -85.76))
print(get_news())
print(get_sports_scores())
print(get_calendar_events())
```

---

## Phase 2 — ADK agent

**`instruction.md`** — the agent's personality and output contract. Lives in a separate file so it can be tuned without rebuilding the image.

```markdown
You are a friendly personal assistant delivering a daily morning briefing.

Call each tool to collect the data, then compose a single Discord message.

Rules:
1. Stay under 1500 characters total.
2. Use this section order with emoji headers:
   ☀️ **Weather** — one sentence
   📰 **News** — up to 3 bullet points
   🏈⚾🏈 **Sports** — one line per league; omit leagues with no active games
   📅 **Calendar** — bullet list; say "Nothing scheduled" if empty
3. End with one short motivational sentence.
4. Never invent data. If a tool failed, say so briefly in that section.
5. Send the finished message using send_discord. Do not ask for confirmation.
```

**`agent.py`** — wires the tools and model together:

```python
import os
from google.adk import Agent
from daily_briefing.tools import (
    get_weather, get_news, get_sports_scores,
    get_calendar_events, send_discord,
)

root_agent = Agent(
    name="daily_briefing",
    model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    description="Daily morning digest agent.",
    instruction=open("daily_briefing/instruction.md").read(),
    tools=[get_weather, get_news, get_sports_scores, get_calendar_events, send_discord],
)
```

**`main.py`** — single-shot runner, no web server, no interactive loop:

```python
import asyncio
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types
from daily_briefing.agent import root_agent

async def run():
    load_dotenv()
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
                "Fetch weather for Wyoming MI, top news, NFL/MLB/CFL scores, "
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
cp .env.example .env  # fill in keys
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
docker run --env-file .env daily-briefing
```

---

## Phase 5 — k8s deployment (high-level)

Standard service pattern in `k3s-homelab/services/daily-briefing/` — same structure as `services/n8n/`:

- `ns.yaml` — namespace
- `external-secret.yaml` — maps 5 Infisical keys into `briefing-secrets`; sync wave `-1`
- `cronjob.yaml` — `schedule: "0 7 * * *"`, `timeZone: "America/Detroit"`, `envFrom: briefing-secrets`, `restartPolicy: OnFailure`
- `kustomization.yaml` — references the three above

**Infisical keys to provision before first sync:**

| Key | Source |
|---|---|
| `google-api-key` | Google AI Studio |
| `news-api-key` | newsapi.org developer account |
| `discord-daily-briefing-webhook` | Discord → Server Settings → Integrations → Webhooks |
| `google-calendar-api-key` | Google Cloud Console → APIs & Services → Credentials |
| `google-calendar-id` | Google Calendar → Calendar Settings → Calendar ID |

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
| Add a stock price | New `get_stock(ticker)` tool in `tools.py`; new line in `instruction.md` |
| SMS instead of / in addition to Discord | Swap or add a `send_sms()` tool (Twilio free trial) |
| Route through n8n | Replace `send_discord()` with a POST to an n8n webhook; n8n handles multi-channel fan-out |
| Try a local LLM | Change `GEMINI_MODEL` env var to an Ollama model string; use `LiteLlm` wrapper as in `minimal_ollama_adk` |
| Weekly digest variant | Duplicate the agent with a different schedule and a `instruction_weekly.md` that asks for a 7-day summary |
