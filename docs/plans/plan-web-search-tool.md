# Plan: Backend-agnostic web-search tool

## Status

**IMPLEMENTED 2026-05-30** with **Tavily** as the provider. Shipped:
`apis/tavily.py`, `tools/web_search.py`, the `else: tools.append(web_search)`
gate in `agent.py`, backend-neutral wording in `instruction.md`, plus
`TAVILY_API_KEY` in `.env.example`, `CLAUDE.md`, and the credentials guide.

**Deviation from the draft below:** the env key is read in the *tool*
(`tools/web_search.py`) and passed into a pure `apis/tavily.search(api_key, ...)`
client — matching the `gnews.py` / `news.py` convention — rather than calling
`os.getenv` inside the API client as the snippet originally showed.

**Verified:** on `BACKEND=github` the agent registers `web_search` (no
`google_search`); on `BACKEND=gemini` it still registers `google_search`; with
`TAVILY_API_KEY` unset the tool returns `"Web search unavailable: TAVILY_API_KEY
not set."` instead of crashing.

**Remaining doc-sync (not yet done):** github-pages `setup.html` env table,
`tools.html` (web_search card + connection-diagram node), `architecture.html`
(system-diagram node + `DETAILS` entry), and a per-backend search note in
`docs/architecture/daily-briefing-design.md`.

## Create a free Tavily account

1. Go to **https://app.tavily.com** and sign up (Google/GitHub SSO or email — no card).
2. The dashboard shows your API key on first load (format `tvly-...`). Copy it.
3. Free tier is ~1,000 searches/month — ample for a personal bot. The dashboard
   shows usage; you can rotate or create additional keys there.
4. Local dev: put it in `daily_briefing/.env` as `TAVILY_API_KEY=tvly-...`.
5. Production (k3s): add it to Infisical and project it via the existing
   `ExternalSecret` — see "K3s / production deployment" below.

## Context

The agent registers ADK's `GoogleSearchTool` for ad-hoc questions. That tool is
Google's **native Gemini grounding** — ADK injects it into the Gemini-API
request and **raises** `ValueError: Google search tool is not supported for
model <x>` for any LiteLLM-routed model. So on `BACKEND=ollama` / `BACKEND=github`
any turn where the model reaches for search crashes the whole reply (e.g.
"who is the top scoring team in MLB right now?" on `github/gpt-4.1`).

A stop-gap is already in place: `models.supports_google_search()` gates
`GoogleSearchTool` to Gemini only (`agent.py`). That stops the crash but leaves
**non-Gemini backends with no web search at all** — the model answers ad-hoc
questions from stale training data or not at all.

This plan adds a **portable web-search tool** — a plain ADK function tool
wrapping a search API — so every backend has search:

- **Gemini** keeps native `google_search` (free, no extra key).
- **Non-Gemini** (`ollama`, `github`) get the portable tool.

## Approach

A function tool is just a Python callable; ADK auto-wraps callables in the
`tools=[...]` list (same as `get_weather` etc.). Follow the repo's existing
split: raw HTTP client under `apis/`, ADK tool under `tools/`. Use `requests`
(already a dependency) rather than a vendor SDK, matching the other `apis/` files.

### New API client: `daily_briefing/apis/tavily.py`

```python
import os
import requests

_URL = "https://api.tavily.com/search"


def search(query: str, max_results: int = 5) -> list[dict]:
    """POST to Tavily; return [{title, url, content}, ...]. Raises on HTTP error."""
    resp = requests.post(
        _URL,
        json={
            "api_key": os.getenv("TAVILY_API_KEY"),
            "query": query,
            "max_results": max_results,
            "include_answer": True,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

### New tool: `daily_briefing/tools/web_search.py`

```python
from daily_briefing.apis.tavily import search


def web_search(query: str) -> str:
    """Search the web for recent or ad-hoc info outside the weather/news/sports/calendar tools."""
    try:
        data = search(query)
    except Exception as exc:
        return f"Web search unavailable: {exc}"  # degrade gracefully, never abort the run
    answer = data.get("answer")
    results = data.get("results", [])
    if not answer and not results:
        return "No web results found."
    lines = [answer] if answer else []
    lines += [f"- {r['title']}: {r['content']} ({r['url']})" for r in results]
    return "\n".join(lines)
```

Graceful-degradation shape (`"... unavailable: ..."` string instead of raising)
matches the other tools per the repo convention.

### Registration: `daily_briefing/agent.py`

Reuse the existing gate — Gemini gets native grounding, everyone else gets the
portable tool:

```python
if supports_google_search():
    tools.append(GoogleSearchTool(bypass_multi_tools_limit=True))
else:
    tools.append(web_search)
```

### Prompt: `daily_briefing/instruction.md`

The prompt currently names `google_search`. Make the search reference
backend-neutral ("use the available web-search tool for ad-hoc questions
outside weather/news/sports/calendar") so it's valid whether the registered
tool is `google_search` or `web_search`.

### Files modified

| File | Change |
|---|---|
| `daily_briefing/apis/tavily.py` | **New.** HTTP client above. |
| `daily_briefing/tools/web_search.py` | **New.** Tool function above. |
| `daily_briefing/agent.py` | `else: tools.append(web_search)` on the existing `supports_google_search()` gate; import `web_search`. |
| `daily_briefing/instruction.md` | Backend-neutral wording for the search tool. |
| `daily_briefing/.env.example` | Add `TAVILY_API_KEY` (required only on non-Gemini backends). |
| `docs/analysis/api-setup-guide.md` | New section: what Tavily is, how to get a key, the "non-Gemini only" note. |
| `CLAUDE.md` | Add `TAVILY_API_KEY` to the env-var table. |
| `docs/github-pages/setup.html` | Same env-var row (docs-sync rule). |
| `docs/github-pages/tools.html` | Add a `web_search` tool card + connection-diagram node. |
| `docs/github-pages/architecture.html` | Add the tool/API node to the system diagram + `DETAILS` entry. |
| `docs/architecture/daily-briefing-design.md` | Note the per-backend search split. |

### Env vars (added)

- `TAVILY_API_KEY` — required **only** when `BACKEND` is `ollama` or `github`.
  On Gemini it's unused (native grounding handles search). LiteLLM/ADK never
  touch it; only `apis/tavily.py` reads it.

## Provider selection

**Recommended: Tavily.** Purpose-built for LLM agents (returns clean,
summarized snippets + an optional synthesized `answer`), simple JSON POST, no
SDK required, generous free tier.

| Provider | Free tier | Auth | Why / why not |
|---|---|---|---|
| **Tavily** (recommended) | ~1,000 searches/mo | `api_key` in body | LLM-optimized results + `answer` field; one POST; no SDK needed. |
| Brave Search API | ~2,000 queries/mo (1 q/s) | `X-Subscription-Token` header | Independent index, privacy-friendly; raw web results (less LLM-shaped). |
| Exa | ~1,000/mo | Bearer | Neural/semantic search; great for research, pricier beyond free. |
| SerpAPI | 100/mo | key in query | Real Google SERP scrape; tiny free tier. |
| Bing Web Search | retiring/azure-gated | Azure key | Azure onboarding overhead; deprioritized. |

All are swappable behind `apis/<provider>.py` — the tool only depends on
`search()` returning `{title, url, content}` dicts, so switching providers is a
one-file change.

## Local dev verification

1. Get a key at https://tavily.com (free tier), set `TAVILY_API_KEY` in `daily_briefing/.env`.
2. `BACKEND=github`, `GITHUB_MODEL=gpt-4.1`.
3. Run `python -m daily_briefing.discord_bot`; ask "who is the top scoring team in MLB right now?" — confirm it calls `web_search` and answers (no `ValueError`).
4. Unset `TAVILY_API_KEY` and re-ask — confirm it degrades to "Web search unavailable: ..." rather than crashing.
5. Flip `BACKEND=gemini` — confirm native `google_search` still registers (7 tools) and nothing regressed.

## K3s / production deployment

PAT-style secret, same pattern as `GITHUB_API_KEY`:

1. Add the key to Infisical as `daily-briefing/tavily-api-key`.
2. Project it via the existing `ExternalSecret` into `briefing-secrets`.
3. In the `Deployment`, set `TAVILY_API_KEY` from that secret. Only needed while
   the deployed bot runs a non-Gemini `BACKEND`; harmless if present otherwise.

## Decision: per-backend vs one search tool everywhere

Chosen: **per-backend** (Gemini → native `google_search`; others → `web_search`).
Keeps Gemini's grounding free (no Tavily quota/key burned when on Gemini).

Alternative considered — **`web_search` on all backends, drop `google_search`
entirely**: simpler and uniform behavior, one code path, easier prompt. But it
throws away Gemini's free native grounding and spends Tavily quota even on the
default backend. Revisit if maintaining two search paths becomes a burden.

## Caveats

- **Another external dependency + key.** A search outage now degrades ad-hoc
  answers on non-Gemini backends; the graceful-degradation string keeps it from
  aborting the run.
- **Free-tier limits.** Tavily ~1,000/mo is ample for a personal bot but is a
  hard cap; heavy ad-hoc use could exhaust it.
- **Result quality differs from Gemini grounding.** Gemini's native search and
  Tavily won't return identical results; answers may vary by backend.

## References

1. ADK `GoogleSearchTool` is Gemini-only — raises for other models:
   `google/adk/tools/google_search_tool.py` (`process_llm_request`).
2. Tavily Search API — https://docs.tavily.com (POST `/search`, `api_key` in body, `answer`/`results` fields).
3. Brave Search API — https://brave.com/search/api/
4. GitHub Models has no Gemini (removed May 2026), so native grounding is unavailable there — https://github.blog/changelog/2026-05-20-updates-to-available-models-in-copilot-on-web/
5. Related: [`plan-github-models-backend.md`](plan-github-models-backend.md) (the backend this gap surfaced on).
