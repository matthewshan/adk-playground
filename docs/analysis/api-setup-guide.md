# API Account Setup Guide

This guide covers credentials required by `daily_briefing`.

---

## 1) Google AI Studio — Gemini API Key

**Used for:** LLM responses when `BACKEND=gemini`.

### Steps
1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. Create an API key.
3. Copy the value into `daily_briefing/.env`.

### Environment variables
```dotenv
BACKEND=gemini
GEMINI_API_KEY=<your key>
# Optional override
GEMINI_MODEL=gemini-3.5-flash
```

---

## 2) GNews — Top Headlines

**Used for:** `get_news()` in `daily_briefing/tools/news.py`.

### Steps
1. Go to [https://gnews.io](https://gnews.io).
2. Create a free account and generate an API key.
3. Add it to `daily_briefing/.env`.

### Environment variable
```dotenv
GNEWS_API_KEY=<your key>
```

---

## 3) Discord — Incoming Webhook URL

**Used for:** `send_discord()` in `daily_briefing/tools/discord_webhook.py`.

### Steps
1. In Discord: **Server Settings → Integrations → Webhooks**.
2. Create a webhook and copy the URL.
3. Add it to `daily_briefing/.env`.

### Environment variable
```dotenv
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
```

---

## 4) Google Calendar (private)

**Used for:** `get_calendar_events()` in `daily_briefing/tools/calendar_events.py`.

Full setup guide:

[google-calendar-private-setup.md](./google-calendar-private-setup.md)

### Environment variables
```dotenv
GOOGLE_CALENDAR_ID=<your-calendar-id>@group.calendar.google.com
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=<base64-encoded service account JSON>
```

---

## 5) `.env` file location

`daily_briefing/main.py` and `daily_briefing/test_apis.py` load env from:
- `daily_briefing/.env`

Create it from the example:

```bash
cp daily_briefing/.env.example daily_briefing/.env
```
