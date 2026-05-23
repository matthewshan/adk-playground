# API Account Setup Guide

This document explains how to obtain the API credentials needed by the daily briefing agent. Each section covers what the key is used for, where to create it, any limits to be aware of, and the exact environment variable name to use.

---

## 1. Google AI Studio — Gemini API Key

**Used for:** The LLM that synthesises the briefing (`gemini-2.0-flash`).

### Steps
1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) and sign in with a Google account.
2. Click **Create API key** → choose or create a Google Cloud project when prompted.
3. Copy the generated key.

### Limits (free tier)
- 15 RPM, 1 million tokens/day for Gemini 2.0 Flash.
- More than sufficient for one daily run.

### Environment variable
```
GEMINI_API_KEY=<your key>
```

> **Note:** `google-adk` reads `GEMINI_API_KEY` automatically. You do **not** need to pass it explicitly to the Agent.

---

## 2. GNews — General Top Headlines

**Used for:** `get_news()` — the 5 general headlines block.

### Steps
1. Go to [https://gnews.io](https://gnews.io) and click **Get API Key**.
2. Create a free account (email + password, no credit card).
3. Copy the API key from your dashboard.

### Limits (free tier)
| Limit | Value |
|---|---|
| Requests per day | 100 |
| Articles per request | Up to 10 |
| Historical data | 1 month |
| Server-side requests | Localhost only on free tier |

The agent makes 1 GNews request per run, so 100 req/day = 100 runs before hitting the limit.

> **Note:** The GNews free tier restricts server-side requests to localhost. This is fine for local development; a paid plan is required for cloud/production deployments.

### Environment variable
```
GNEWS_API_KEY=<your key>
```

---

## 3. Discord — Incoming Webhook URL

**Used for:** `send_discord()` — posting the finished briefing.

### Steps
1. Open the Discord server where you want the briefing to be posted.
2. Go to **Server Settings → Integrations → Webhooks**.
3. Click **New Webhook**, give it a name (e.g. `Daily Briefing`), choose the target channel, and click **Copy Webhook URL**.

### Limits
- No rate limits for a single daily POST.
- The webhook URL is a secret — treat it like a password. Anyone with the URL can post to your channel.

### Environment variable
```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
```

---

## 4. Google Calendar

Setting up a private Google Calendar requires a GCP service account. See the dedicated guide:

[google-calendar-private-setup.md](./google-calendar-private-setup.md)

### How access works

Terraform in the external
[`cloud-infrastructure/terraform-adk-agents`](https://github.com/matthewshan/cloud-infrastructure/tree/main/terraform-adk-agents)
directory handles the GCP side; calendar sharing is a one-time manual step:

1. **Terraform provisions** (automated):
   - Enables the Calendar API in your GCP project
   - Creates a service account: `daily-briefing-agent@<project-id>.iam.gserviceaccount.com`
   - Generates a JSON key for that account

2. **You share the calendar** (manual, one-time):
   - Open [calendar.google.com](https://calendar.google.com)
   - Hover your calendar → three-dot menu → **Settings and sharing**
   - **Share with specific people** → add the service account email from the Terraform output
   - Set permission to **See all event details** (read-only) → Send
   - The share takes effect immediately — no acceptance needed

3. **The agent authenticates** at runtime using `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` from `.env`, and because your calendar is shared with that service account, the Calendar API returns your events.

### Environment variables (summary)
```
GOOGLE_CALENDAR_ID=<your-calendar-id>@group.calendar.google.com
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=<base64-encoded service account JSON>
```

---

## 5. `.env.example` reference

The daily briefing example env file lives at `daily_briefing/.env.example`. Copy it to
`daily_briefing/.env` and fill in your values before running locally:

```bash
cp daily_briefing/.env.example daily_briefing/.env
```

```dotenv
# Google AI (Gemini)
GEMINI_API_KEY=

# GNews
GNEWS_API_KEY=

# Discord
DISCORD_WEBHOOK_URL=

# Google Calendar (private — via service account)
GOOGLE_CALENDAR_ID=
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=

# Optional — override Gemini model
GEMINI_MODEL=gemini-2.0-flash
```
