# Plan: Daily Briefing ADK Agent

Build a "Daily Pulse" agent in `adk-playground` that fetches weather, breaking news, sports scores (NFL, MLB, CFL), and Google Calendar events every morning, uses Gemini Flash (free tier) to summarize them into a friendly digest, and posts the result to a Discord webhook. The agent runs as a Kubernetes `CronJob` in the `matthewshan/k3s-homelab` cluster, managed by Argo CD, with all secrets backed by Infisical through External Secrets.

---

## Architecture Summary

```
CronJob trigger (7:00 AM daily)
  └─► daily_briefing/main.py
        ├─ Parallel tool calls
        │    ├─ get_weather()       → Open-Meteo (no key)
        │    ├─ get_news()          → NewsAPI (free tier key)
        │    ├─ get_sports()        → API-Sports or ESPN hidden API (free)
        │    └─ get_calendar()      → Google Calendar API (key)
        ├─ Gemini Flash summarizes raw JSON → friendly digest text
        └─ send_discord()           → Discord webhook POST
```

No long-running service. No ingress. No PVC. The pod runs for ~10–20 seconds and exits.

---

## Tech Stack Decisions

| Concern | Choice | Rationale |
|---|---|---|
| LLM | `gemini-2.0-flash` via free Gemini API | Generous free quota, fast, no GPU needed |
| Weather | Open-Meteo REST API | Free, no API key, reliable |
| News | NewsAPI.org developer tier | Free tier; 100 req/day is plenty for one daily call |
| Sports | `api-sports.io` (free tier) or `site.api.espn.com` (unofficial, no key) | ESPN unofficial endpoints cover NFL, MLB; CFL needs api-sports.io |
| Calendar | Google Calendar API (OAuth2 service account or API key + Calendar ID) | Already in Google ecosystem with Gemini |
| Delivery | Discord webhook | No bot setup; single `requests.post()` call |
| Secrets | Infisical → External Secrets → Kubernetes Secret | Matches existing homelab pattern exactly |
| Schedule | Kubernetes CronJob | Zero idle cost; no ingress needed |
| Image registry | `ghcr.io/matthewshan/daily-briefing` | Free for public repos; no cluster pull secret needed |

---

## Phase 1 — Python Agent in `adk-playground`

### 1.1  Create `daily_briefing/` module

New directory alongside `minimal_ollama_adk/`:

```
daily_briefing/
  __init__.py
  agent.py        ← ADK agent definition + tool registrations
  tools.py        ← all API tool functions
  main.py         ← entrypoint; runs agent once and exits
  instruction.md  ← system prompt kept separate for easy iteration
```

### 1.2  `daily_briefing/tools.py`

Define one Python function per data source. ADK auto-converts typed functions to tool definitions.

**`get_weather(latitude: float, longitude: float) -> str`**

- URL: `https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weathercode,windspeed_10m&temperature_unit=fahrenheit`
- No API key required
- Default coords for Wyoming, MI: `latitude=42.70`, `longitude=-85.76`
- Return a short human-readable string: `"72°F, clear sky, wind 8 mph"`

**`get_news(query: str = "breaking news") -> str`**

- URL: `https://newsapi.org/v2/top-headlines?language=en&pageSize=5&apiKey={NEWS_API_KEY}`
- Returns the top 5 headline titles + sources as a bulleted string
- Key from env: `NEWS_API_KEY`

**`get_sports_scores(leagues: list[str] = ["NFL", "MLB", "CFL"]) -> str`**

- Primary: ESPN unofficial API (no key) — endpoint pattern:
  - NFL: `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`
  - MLB: `https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard`
- CFL: `https://site.api.espn.com/apis/site/v2/sports/football/cfl/scoreboard` (ESPN does carry CFL)
- Returns yesterday's final scores or "Season not active" if off-season
- No API key needed for ESPN public scoreboards

**`get_calendar_events(days_ahead: int = 1) -> str`**

- Uses Google Calendar API v3: `GET /calendars/{calendarId}/events`
- Requires `GOOGLE_CALENDAR_ID` (public calendar ID or the primary `primary` alias)
- Auth: Simple API key works for public calendars; for private calendars use a service account JSON (store in Infisical as a base64-encoded value)
- Returns today's events as a bulleted string
- Key from env: `GOOGLE_CALENDAR_API_KEY` and `GOOGLE_CALENDAR_ID`

**`send_discord(message: str) -> str`**

- `POST {DISCORD_WEBHOOK_URL}` with `{"content": message}`
- Key from env: `DISCORD_WEBHOOK_URL`
- Returns `"Sent"` on 204 or raises on failure (so ADK sees the error)

### 1.3  `daily_briefing/instruction.md`

```markdown
You are a friendly personal assistant delivering a daily morning briefing.

You have already been given the following data:
- Current weather
- Top news headlines
- Sports scores for NFL, MLB, and CFL
- Today's calendar events

Your job:
1. Summarize all four sections into a single Discord message under 1500 characters.
2. Use simple language and add relevant emojis to each section header.
3. Use this structure exactly:
   ☀️ **Weather** — one sentence
   📰 **News** — 3 bullet points max
   🏈⚾🏈 **Sports** — one line per league; skip leagues with no active games
   📅 **Calendar** — bullet list of today's events; say "Nothing scheduled" if empty
4. End with a short motivational sentence.
5. Never make up data. If a tool returned an error, say so briefly in that section.
```

### 1.4  `daily_briefing/agent.py`

```python
import os
from google.adk import Agent
from google.adk.tools import tool
from daily_briefing.tools import (
    get_weather, get_news, get_sports_scores,
    get_calendar_events, send_discord
)

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

root_agent = Agent(
    name="daily_briefing",
    model=MODEL,
    description="Fetches daily weather, news, sports, and calendar data and posts a morning digest to Discord.",
    instruction=open("daily_briefing/instruction.md").read(),
    tools=[
        tool(get_weather),
        tool(get_news),
        tool(get_sports_scores),
        tool(get_calendar_events),
        tool(send_discord),
    ],
)
```

### 1.5  `daily_briefing/main.py`

Single-shot runner — no interactive loop, no web server:

```python
import asyncio
import os
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types
from daily_briefing.agent import root_agent

APP_NAME = "daily_briefing"
USER_ID = "scheduler"

async def run_briefing():
    load_dotenv()
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    prompt = (
        "Fetch the weather for Wyoming, MI (lat 42.70, lon -85.76), "
        "get top news headlines, get sports scores for NFL, MLB, and CFL, "
        "get today's calendar events, then compose and send the morning digest to Discord."
    )
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text)

if __name__ == "__main__":
    asyncio.run(run_briefing())
```

### 1.6  Update `requirements.txt`

Add the new dependencies (check `google-adk` already pulls `google-generativeai`; add only what is missing):

```
google-adk[extensions]
python-dotenv
requests
google-auth
google-api-python-client
```

### 1.7  `Dockerfile`

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

### 1.8  GitHub Actions: `.github/workflows/docker-publish.yml`

Trigger: push to `main` on any change under `daily_briefing/` or `Dockerfile`.

Steps:
1. Checkout
2. Log in to ghcr.io using `GITHUB_TOKEN`
3. Build and push `ghcr.io/matthewshan/daily-briefing:latest` and `ghcr.io/matthewshan/daily-briefing:<git-sha>`

The image is public (repo is public) so the k3s cluster pulls it without a `imagePullSecret`.

---

## Phase 2 — Kubernetes Manifests in `k3s-homelab`

Add `services/daily-briefing/` following the same flat-file pattern as `services/n8n/`.

### 2.1  `services/daily-briefing/ns.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: daily-briefing
```

### 2.2  `services/daily-briefing/external-secret.yaml`

Sync wave `-1` so the secret exists before the CronJob pod runs.

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: briefing-secrets
  namespace: daily-briefing
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: infisical
  target:
    name: briefing-secrets
    creationPolicy: Owner
  data:
    - secretKey: GOOGLE_API_KEY
      remoteRef:
        key: google-api-key
    - secretKey: NEWS_API_KEY
      remoteRef:
        key: news-api-key
    - secretKey: DISCORD_WEBHOOK_URL
      remoteRef:
        key: discord-daily-briefing-webhook
    - secretKey: GOOGLE_CALENDAR_API_KEY
      remoteRef:
        key: google-calendar-api-key
    - secretKey: GOOGLE_CALENDAR_ID
      remoteRef:
        key: google-calendar-id
```

### 2.3  `services/daily-briefing/cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-briefing
  namespace: daily-briefing
spec:
  schedule: "0 11 * * *"   # 7:00 AM EST = 11:00 UTC; adjust for DST
  timeZone: "America/Detroit"  # requires k8s 1.27+; k3s v1.35 supports it
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 300
      template:
        spec:
          restartPolicy: OnFailure
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
          containers:
            - name: agent
              image: ghcr.io/matthewshan/daily-briefing:latest
              envFrom:
                - secretRef:
                    name: briefing-secrets
              resources:
                requests:
                  cpu: 100m
                  memory: 128Mi
                limits:
                  cpu: 500m
                  memory: 256Mi
```

**Notes on schedule:**
- `timeZone: "America/Detroit"` is a k8s 1.27+ field. k3s `v1.35.2+k3s1` supports it.
- During EDT (UTC-4): 7 AM = 11:00 UTC. During EST (UTC-5): 7 AM = 12:00 UTC.
- Using `timeZone` field avoids manually updating the UTC offset twice a year.

### 2.4  `services/daily-briefing/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ns.yaml
  - external-secret.yaml
  - cronjob.yaml

namespace: daily-briefing
```

### 2.5  No changes to `services/services-appset.yaml`

The existing ApplicationSet generator discovers all `services/*` directories automatically. Committing `services/daily-briefing/` to `main` is sufficient for Argo CD to pick it up.

---

## Phase 3 — Infisical Secret Bootstrap

Before the first Argo CD sync, add these five keys to Infisical:

| Infisical key | Where to get it |
|---|---|
| `google-api-key` | [Google AI Studio](https://aistudio.google.com/app/apikey) — free Gemini quota |
| `news-api-key` | [newsapi.org](https://newsapi.org/register) — free developer account |
| `discord-daily-briefing-webhook` | Discord → Server Settings → Integrations → Webhooks → New Webhook → Copy URL |
| `google-calendar-api-key` | Google Cloud Console → APIs & Services → Credentials → API key (restrict to Calendar API) |
| `google-calendar-id` | Google Calendar → Settings → `Calendar ID` field (e.g. `primary` or full email address for your main calendar) |

No `kubectl create secret` command is needed. External Secrets creates `briefing-secrets` in the `daily-briefing` namespace automatically after the ExternalSecret is synced.

**Note on Google Calendar API key:** API keys only work for public calendars. For a private calendar, create a service account instead:
1. Google Cloud Console → IAM → Service Accounts → Create
2. Share your calendar with the service account email (view-only)
3. Download the JSON key
4. Base64-encode it: `base64 -w0 service-account.json`
5. Store the base64 string in Infisical as `google-calendar-service-account-json`
6. Update `external-secret.yaml` to add the new key and update `tools.py` to decode and use it via `google.oauth2.service_account.Credentials`

---

## Phase 4 — First Run Validation

1. **Local smoke test** — set env vars manually and run:
   ```bash
   export GOOGLE_API_KEY=...
   export NEWS_API_KEY=...
   export DISCORD_WEBHOOK_URL=...
   export GOOGLE_CALENDAR_API_KEY=...
   export GOOGLE_CALENDAR_ID=primary
   python -m daily_briefing.main
   ```
   Confirm a Discord message arrives.

2. **Container test** — build locally and test:
   ```bash
   docker build -t daily-briefing .
   docker run --env-file .env daily-briefing
   ```

3. **Image push** — merge to `main`; confirm `ghcr.io/matthewshan/daily-briefing:latest` appears in GitHub Packages.

4. **kustomize render** — in the `k3s-homelab` repo:
   ```bash
   kubectl kustomize services/daily-briefing
   ```
   Should produce valid YAML with no missing refs.

5. **Argo CD sync** — after merge, watch Argo CD autodiscover the `daily-briefing` application and sync. Check:
   ```bash
   kubectl get externalsecret -n daily-briefing      # should show Ready
   kubectl get secret briefing-secrets -n daily-briefing
   kubectl get cronjob -n daily-briefing
   ```

6. **Manual trigger** — force a one-off run to verify end-to-end before waiting for 7 AM:
   ```bash
   kubectl create job --from=cronjob/daily-briefing manual-test -n daily-briefing
   kubectl logs -f job/manual-test -n daily-briefing
   ```

---

## Relevant Files

**In `adk-playground` (new):**

| File | Purpose |
|---|---|
| `daily_briefing/__init__.py` | Package init (empty) |
| `daily_briefing/instruction.md` | System prompt; edit without touching Python |
| `daily_briefing/tools.py` | All five tool functions |
| `daily_briefing/agent.py` | ADK `Agent` definition wiring tools and model |
| `daily_briefing/main.py` | Single-shot runner for CronJob |
| `Dockerfile` | Container image for the CronJob pod |
| `.github/workflows/docker-publish.yml` | Build and push to ghcr.io on `main` |

**In `adk-playground` (changed):**

| File | Change |
|---|---|
| `requirements.txt` | Add `requests`, `google-auth`, `google-api-python-client` |

**In `k3s-homelab` (new):**

| File | Purpose |
|---|---|
| `services/daily-briefing/ns.yaml` | Namespace |
| `services/daily-briefing/external-secret.yaml` | Maps 5 Infisical keys → `briefing-secrets` |
| `services/daily-briefing/cronjob.yaml` | Scheduled CronJob with secret injection |
| `services/daily-briefing/kustomization.yaml` | Kustomize root for the service |
| `services/daily-briefing/README.md` | Documents Infisical key contract and manual trigger commands |

**In `k3s-homelab` (unchanged):**

- `services/services-appset.yaml` — autodiscovers `services/daily-briefing/`
- All `infrastructure/` components

---

## Decisions

- **CronJob, not a Deployment** — The briefing is a batch task. A CronJob has zero idle cost and zero ingress surface. An always-on `Deployment` would be wasteful for a script that runs once a day.
- **Gemini Flash free tier** — The free quota (15 req/min, 1500 req/day, 1M tokens/day as of mid-2026) is far beyond what one daily call needs. No cost, much better quality than a local small model for this summarization task.
- **ESPN unofficial API for sports** — No API key required, returns current scores in JSON. If ESPN ever breaks this endpoint, replace with `api-sports.io` which has a 100 req/day free tier.
- **Open-Meteo for weather** — Completely free and no key required. Already familiar from the Gemini session example.
- **`instruction.md` kept separate** — Per the ADK pattern in `docs/context-engineering.md`, the prompt lives in a separate file so it can be iterated without rebuilding the image.
- **`envFrom: secretRef`** — Using `envFrom` instead of individual `env[*].valueFrom` keeps the CronJob YAML shorter and avoids needing to update the manifest when adding a new key.

---

## Further Considerations

1. **DST handling** — The `timeZone` field in `CronJob.spec` handles Daylight Saving automatically. No cron schedule update needed each spring/fall.

2. **Private Google Calendar** — If the calendar is private, the API key approach will not work. A service account is slightly more setup but gives a proper OAuth2 flow. See Phase 3 note above.

3. **Adding tools later** — Each new data source is one new function in `tools.py` and one new `tool(...)` entry in `agent.py`. The instruction in `instruction.md` may need one new section header. The k8s manifests stay unchanged unless a new API key is needed.

4. **Sports off-season** — `get_sports_scores()` should return `"No games today (off-season)"` gracefully rather than an error when there is no scoreboard data. The agent's instruction already handles this ("skip leagues with no active games").

5. **Log visibility** — Check digest delivery failures via:
   ```bash
   kubectl logs -l job-name=daily-briefing -n daily-briefing --tail=100
   ```
   Argo CD also surfaces CronJob status and recent job history in its UI.

6. **Extending to text/SMS** — Discord is the lowest-friction delivery, but Twilio (free trial credits) or a Pushover notification could replace or augment it by swapping `send_discord()` for a different delivery tool. No architectural change needed.

7. **n8n integration** — If n8n workflows already run in the cluster, the `send_discord()` tool could be replaced with a `POST` to an n8n webhook that routes the digest to multiple channels (Discord + email + Slack) from a single n8n flow.
