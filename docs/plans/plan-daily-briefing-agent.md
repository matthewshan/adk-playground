# Plan: Daily Briefing ADK Agent

This plan is aligned with the current repository implementation and tracks next-step improvements.

---

## Current state (implemented)

- `daily_briefing/agent.py` wires the ADK root agent and tool set.
- Backend selection is environment-driven:
  - `BACKEND=gemini` (default, `GEMINI_MODEL` default `gemini-3.5-flash`)
  - `BACKEND=ollama` (local model via LiteLlm)
- Tool modules are split by API under `daily_briefing/tools/`:
  - `weather.py`, `news.py`, `sports.py`, `calendar_events.py`, `discord_webhook.py`
- `daily_briefing/main.py` runs a single-shot workflow with `InMemoryRunner`.
- `daily_briefing/test_apis.py` provides smoke checks for all tools.

---

## Near-term plan

- [ ] Add stronger input validation and clearer error messaging in tool outputs.
- [ ] Add deterministic unit tests with mocked API responses per tool.
- [ ] Add retries/backoff for transient HTTP/API failures.
- [ ] Add lightweight observability (tool timing/status) for easier debugging.
- [ ] Finalize container + CronJob rollout described in `docs/plans/plan-adk-k8s-deployment.md`.

---

## Operational checklist

- [ ] Keep `daily_briefing/.env.example` synchronized with runtime env vars.
- [ ] Keep docs synchronized when tool contracts, env vars, or file paths change.
- [ ] Re-run smoke checks after major changes:
  - `python3 daily_briefing/test_apis.py`

---

## Related docs

- Architecture: `docs/architecture/daily-briefing-design.md`
- API setup: `docs/analysis/api-setup-guide.md`
- Calendar setup: `docs/analysis/google-calendar-private-setup.md`
- Deployment plan: `docs/plans/plan-adk-k8s-deployment.md`
