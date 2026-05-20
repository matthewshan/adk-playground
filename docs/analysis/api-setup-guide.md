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

## 2. NewsAPI.org — News API Key

**Used for:** `get_news()` — general top headlines + cloud/AI topic filtering.

### Steps
1. Go to [https://newsapi.org/register](https://newsapi.org/register) and create a free developer account.
2. After email verification, your API key is shown on the dashboard under **API Key**.
3. Copy it.

### Limits (free / developer tier)
| Limit | Value |
|---|---|
| Requests per day | 100 |
| Results per request | Up to 100 |
| Delay on free tier | Headlines are ~15 minutes behind live |
| Domains allowed | `localhost` and `127.0.0.1` only on free tier |

The agent makes 3 requests per run (general, cloud, AI), so 100 req/day gives ~33 runs/day — well within budget.

> **Important:** The free developer plan restricts requests to localhost. This is fine for local testing and for a k8s CronJob (which makes server-side requests, not browser requests). If NewsAPI rejects requests with a `426 Upgrade Required`, you may need to pass `X-Api-Key` header instead of a query parameter — `tools.py` already does this correctly.

### Environment variable
```
NEWS_API_KEY=<your key>
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

### Environment variables (summary)
```
GOOGLE_CALENDAR_ID=<your-calendar-id>@group.calendar.google.com
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=<base64-encoded service account JSON>
```

---

## 5. `.env.example` reference

A complete `.env.example` is at the repo root. Copy it to `.env` and fill in your values before running locally:

```bash
cp .env.example .env
```

```dotenv
# Google AI (Gemini)
GEMINI_API_KEY=

# NewsAPI
NEWS_API_KEY=

# Discord
DISCORD_WEBHOOK_URL=

# Google Calendar (private — via service account)
GOOGLE_CALENDAR_ID=
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=

# Optional — override Gemini model
GEMINI_MODEL=gemini-2.0-flash
```
