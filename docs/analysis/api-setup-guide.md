# Environment & Credentials Guide

Every secret the daily-briefing agent needs lives in `daily_briefing/.env` (never
committed). The `.env.example` file is intentionally terse — **this document is the
explanation**: for each variable it covers what it's for, when it's required, how to
obtain the value, and any limits or gotchas.

```bash
cp daily_briefing/.env.example daily_briefing/.env   # then fill in the values below
```

## Quick reference

| Variable | Required when | What it is |
|---|---|---|
| `BACKEND` | optional (default `gemini`) | Which LLM powers the briefing: `gemini`, `ollama`, or `github` |
| `GEMINI_API_KEY` | **always** | Gemini LLM (if `BACKEND=gemini`) **and** memory embeddings (all backends) |
| `GEMINI_MODEL` | optional | Override the Gemini chat model (default `gemini-3.1-flash-lite`) |
| `GITHUB_API_KEY` | if `BACKEND=github` | Fine-grained GitHub PAT with `Models: read` |
| `GITHUB_MODEL` | optional | GitHub Models model id (default `gpt-4.1`) |
| `OLLAMA_API_BASE` | if `BACKEND=ollama` | URL of your local Ollama server |
| `OLLAMA_MODEL` | if `BACKEND=ollama` | Local model name (e.g. `qwen2.5:7b`) |
| `GNEWS_API_KEY` | for news | GNews free-tier API key |
| `TAVILY_API_KEY` | if `BACKEND` is `ollama`/`github` | Tavily web-search key for the portable `web_search` tool (Gemini uses native `google_search`) |
| `DISCORD_BOT_TOKEN` | to run the bot | Discord bot token |
| `DISCORD_BOT_CHANNEL_ID` | to run the bot | Channel the bot posts to and listens in |
| `GOOGLE_CALENDAR_ID` | for calendar | Calendar address to read events from |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | for calendar | Base64-encoded GCP service-account key |
| `SUPABASE_URL` | optional | Supabase project URL — enables long-term memory |
| `SUPABASE_SERVICE_ROLE_KEY` | optional | Supabase service-role key |

> **The one non-obvious dependency:** `GEMINI_API_KEY` is needed *even when you pick a
> non-Gemini backend*. The chat LLM is pluggable, but long-term memory always embeds
> text with Google's `gemini-embedding-001` model (see
> [§ Supabase](#8-supabase--long-term-memory-optional)). Without it, memory degrades
> silently — the briefing still prints, it just won't persist.

---

## 1. `BACKEND` — choosing the LLM

Picks which provider answers the briefing. One of:

| Value | Model source | Also needs |
|---|---|---|
| `gemini` (default) | Google AI Studio | `GEMINI_API_KEY` |
| `github` | GitHub Models (OpenAI-compatible) | `GITHUB_API_KEY` |
| `ollama` | A local Ollama server | `OLLAMA_API_BASE`, `OLLAMA_MODEL` |

```dotenv
BACKEND=github
```

Backend selection lives in `daily_briefing/models.py` (`make_model()`), one helper per
provider. Regardless of choice, memory embeddings still use Gemini (see the note above).

---

## 2. Google AI Studio — `GEMINI_API_KEY`

**Used for:** the chat LLM when `BACKEND=gemini`, **and** memory embeddings
(`gemini-embedding-001`) on every backend.

### Steps
1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) and sign in.
2. Click **Create API key** → choose or create a Google Cloud project.
3. Copy the generated key.

### Limits (free tier)
- ~15 RPM and a generous daily token budget for Flash-Lite — far more than one daily run.

### Environment variables
```dotenv
GEMINI_API_KEY=<your key>
# GEMINI_MODEL=gemini-3.1-flash-lite   # optional override
```

> `google-adk` reads `GEMINI_API_KEY` automatically — you don't pass it to the Agent.

---

## 3. GitHub Models — `GITHUB_API_KEY`

**Used for:** the chat LLM when `BACKEND=github`. GitHub Models is GitHub's official
OpenAI-compatible inference endpoint, routed through LiteLLM's `github/*` provider.

### Steps
1. Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Fine-grained tokens** → **Generate new token**.
2. Set **Resource owner** to your own account (not an org, unless that org has GitHub Models enabled).
3. Under **Account permissions → Models**, set **Read-only**. *That is the only permission needed* — no repository access.
4. Generate and copy the token.

### Notes & limits
- Rate limits scale with your Copilot tier (Free / Pro / Business / Enterprise).
- Default `GITHUB_MODEL=gpt-4.1` draws **0× credits** on Copilot Pro. See the fallback
  ladder in `daily_briefing/.env.example` and the full catalog at
  [github.com/marketplace/models](https://github.com/marketplace/models).
- Use the **bare** model id (`gpt-4.1`), not `openai/gpt-4.1` — LiteLLM strips company prefixes.
- A `403 No access to model: …` means that model isn't on your plan/region — not a token-scope problem.

### Environment variables
```dotenv
GITHUB_API_KEY=<fine-grained PAT>
GITHUB_MODEL=gpt-4.1
BACKEND=github
```

---

## 4. Ollama — local models (optional)

**Used for:** running the briefing entirely on a local model, no cloud LLM.

### Steps
1. Install Ollama and start the server (`ollama serve`).
2. Pull a tool-calling-capable model, e.g. `ollama pull qwen2.5:7b`.

### Environment variables
```dotenv
OLLAMA_API_BASE=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
BACKEND=ollama
```

`qwen2.5:7b` (~4.5 GB) fits in 8 GB VRAM and does tool calling reliably.

---

## 5. GNews — `GNEWS_API_KEY`

**Used for:** `get_news()` — the general headlines block.

### Steps
1. Go to [gnews.io](https://gnews.io) → **Get API Key**.
2. Create a free account (email + password, no card).
3. Copy the key from your dashboard.

### Limits (free tier)
| Limit | Value |
|---|---|
| Requests/day | 100 |
| Articles/request | up to 10 |
| Server-side requests | **localhost only** |

The agent makes 1 request per run. The localhost restriction is fine for local dev; a
paid plan is required for cloud/production deployment.

### Environment variable
```dotenv
GNEWS_API_KEY=<your key>
```

---

## 6. Discord bot — `DISCORD_BOT_TOKEN` + `DISCORD_BOT_CHANNEL_ID`

**Used for:** the long-running bot that posts the 7 AM briefing and handles conversation.
This replaces the old incoming-webhook approach (the webhook client is kept only for
manual use). Full walkthrough: [discord-bot-setup.md](./discord-bot-setup.md).

### Steps (summary)
1. [Discord Developer Portal](https://discord.com/developers/applications) → **New Application** → **Bot** → **Reset/Copy Token** → `DISCORD_BOT_TOKEN`.
2. Enable the **Message Content Intent** under the bot settings.
3. Invite the bot to your server with the **Send Messages** / **Read Message History** scopes.
4. In Discord, enable Developer Mode, right-click the target channel → **Copy Channel ID** → `DISCORD_BOT_CHANNEL_ID`.

### Environment variables
```dotenv
DISCORD_BOT_TOKEN=<bot token>
DISCORD_BOT_CHANNEL_ID=<channel id>
```

> The token is a secret — anyone with it controls your bot. Never commit it.

---

## 7. Google Calendar — `GOOGLE_CALENDAR_ID` + `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`

**Used for:** `get_calendar_events()` — today's agenda. Reading a private calendar uses a
GCP service account. Full guide: [google-calendar-private-setup.md](./google-calendar-private-setup.md).

### How access works
1. **Terraform provisions** (automated, in the external
   [`cloud-infrastructure/terraform-adk-agents`](https://github.com/matthewshan/cloud-infrastructure/tree/main/terraform-adk-agents)):
   enables the Calendar API, creates the service account
   `daily-briefing-agent@<project-id>.iam.gserviceaccount.com`, and generates a JSON key.
2. **You share the calendar** (one-time, manual): [calendar.google.com](https://calendar.google.com)
   → your calendar → **Settings and sharing** → **Share with specific people** → add the
   service-account email → **See all event details** (read-only). Takes effect immediately.
3. **The agent authenticates** at runtime with `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`.

### Producing the base64 value
```bash
# from the downloaded service-account JSON key file
base64 -w0 service-account.json    # Linux
# PowerShell:
[Convert]::ToBase64String([IO.File]::ReadAllBytes("service-account.json"))
```

### Environment variables
```dotenv
GOOGLE_CALENDAR_ID=<your-calendar-id>@group.calendar.google.com   # or a plain email address
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=<base64 of the JSON key>
```

---

## 8. Supabase — long-term memory (optional)

**Used for:** pgvector-backed long-term memory (`SupabaseMemoryService`). When unset, the
bot warns once and runs without persistent memory. Schema setup:
[supabase-vector-adk.md](../integrations/supabase-vector-adk.md).

### Steps
1. Create a project at [supabase.com](https://supabase.com).
2. **Settings → API** → copy the **Project URL** and the **`service_role`** key (not `anon`).
3. Apply the pgvector schema from the integration guide above.

### Environment variables
```dotenv
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role key>
```

> Memory embeds every turn with Gemini's `gemini-embedding-001`, so enabling Supabase
> also requires a working `GEMINI_API_KEY` — see the note at the top of this guide.

---

## Minimum to run

| Goal | Required variables |
|---|---|
| Print a digest (`smoke_tests/test_agent.py`) on `BACKEND=github` | `GITHUB_API_KEY`, `GNEWS_API_KEY`, calendar vars; `GEMINI_API_KEY` only if you want memory to persist |
| Print a digest on `BACKEND=gemini` | `GEMINI_API_KEY`, `GNEWS_API_KEY`, calendar vars |
| Run the full Discord bot | the above **plus** `DISCORD_BOT_TOKEN`, `DISCORD_BOT_CHANNEL_ID` |
| Long-term memory | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY` |
