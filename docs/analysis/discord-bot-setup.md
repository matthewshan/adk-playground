# Discord Bot Setup Guide

This document covers everything you need to run the `daily_briefing` Discord bot —
from creating the bot in the Discord Developer Portal to configuring environment
variables and understanding how sessions work.

---

## What the bot does

The bot is a single long-running process that owns **all** agent interactions:

- **Scheduled briefing** — fires daily at 7 AM Eastern via `discord.ext.tasks`.
  Posts the morning digest directly to the configured channel.
- **Conversational** — each Discord user in the configured channel gets their own
  independent ADK session. Context is maintained in-memory for the lifetime of
  the bot process. Past sessions are persisted to Supabase for long-term semantic
  recall via the agent's `LoadMemoryTool`.

---

## 1. Create a Discord application and bot

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications) and sign in.
2. Click **New Application**, give it a name (e.g. `Daily Briefing`), and confirm.
3. In the left sidebar, select **Bot**.
4. Click **Reset Token** (or **Copy** if a token is already shown) and save it — this is `DISCORD_BOT_TOKEN`.
5. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
   (The bot needs this to read the text of messages in the channel.)

---

## 2. Invite the bot to your server

1. In the left sidebar, select **OAuth2 → URL Generator**.
2. Under **Scopes**, check **bot**.
3. Under **Bot Permissions**, check:
   - **Send Messages**
   - **Read Message History**
4. Copy the generated URL and open it in a browser. Select your server and click **Authorize**.

---

## 3. Get the channel ID

1. In Discord, open **User Settings → Advanced** and enable **Developer Mode**.
2. Right-click the channel where the bot should listen and post, then select **Copy Channel ID**.
3. This integer is `DISCORD_BOT_CHANNEL_ID`.

---

## 4. Environment variables

Add these to `daily_briefing/.env` (copy from `daily_briefing/.env.example`).

### Required

| Variable | Description |
|---|---|
| `DISCORD_BOT_TOKEN` | Bot token from the Discord Developer Portal (step 1 above) |
| `DISCORD_BOT_CHANNEL_ID` | Integer channel ID where the bot listens and posts |

All other variables required by the agent itself (Gemini key, GNews key, Google
Calendar credentials) must also be set — the same agent runs for both the
scheduled briefing and conversational turns. See
[api-setup-guide.md](./api-setup-guide.md) for instructions on each key.

### Optional — memory persistence

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key for the Supabase project |

If absent, the bot starts without long-term memory and logs a startup warning.
In-process conversational context still works; it just resets when the bot restarts.
See [supabase-vector-adk.md](../integrations/supabase-vector-adk.md) for the schema setup.

---

## 5. Run the bot

```bash
# Install dependencies
python3 -m pip install --user -r requirements.txt

# Copy and fill in env vars
cp daily_briefing/.env.example daily_briefing/.env
# edit daily_briefing/.env

# Start the bot
python3 -m daily_briefing.discord_bot
```

Or with Docker:

```bash
docker build -t daily-briefing-bot -f daily_briefing/Dockerfile.bot .
docker run --env-file daily_briefing/.env daily-briefing-bot
```

---

## 6. Session design

| Aspect | Detail |
|---|---|
| **Per-user isolation** | Each Discord `user_id` maps to its own ADK session. Alice and Bob have independent conversation histories even in the same channel. |
| **Scheduler session** | The scheduled briefing uses `user_id = "scheduler"` — isolated from all per-user sessions. |
| **In-memory lifetime** | Sessions live in RAM and reset when the bot process restarts. |
| **Long-term memory** | After each turn the session is persisted to Supabase via `after_agent_callback`. On the next run the agent can recall past context via `LoadMemoryTool`. |
| **Concurrency** | A per-user `asyncio.Lock` serialises rapid back-to-back messages from the same user so the agent never processes two turns concurrently for one session. |
