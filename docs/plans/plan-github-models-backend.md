# Plan: Add GitHub Models as a third LLM backend

## Context

`daily_briefing/agent.py` currently picks a model inline based on a `BACKEND`
env var with two values: `gemini` (Google AI Studio) and `ollama`. Gemini AI
Studio's free-tier quotas run out quickly under normal daily use of the Discord
bot, so a third backend is needed to take pressure off.

Two changes are made together:

1. **Refactor**: backend-selection logic moves out of `agent.py` into a new
   `daily_briefing/models.py` module. With a third backend going in, keeping
   the switch inline in `agent.py` will keep widening that file every time we
   add or tune a provider.
2. **New backend**: add **GitHub Models** as the third option. GitHub Models
   is GitHub's officially supported, OpenAI-compatible inference API
   (`https://models.github.ai/inference`) — the sanctioned path for calling
   GitHub-hosted LLMs from third-party apps. Rate limits scale with the
   user's GitHub Copilot subscription tier (Pro > Free), so an existing paid
   Copilot subscription directly buys more quota here.

Note on the unofficial alternative: LiteLLM also ships a `github_copilot/*`
provider that impersonates the VS Code Copilot client. That path is **not**
officially sanctioned and is **not** used in this plan. See the LiteLLM
references at the bottom.

## Approach

### New module: `daily_briefing/models.py`

Single public function: `make_model()` returns whatever the ADK `Agent(model=...)`
constructor expects — either a string (for Gemini) or a `LiteLlm` instance
(for Ollama and GitHub Models). Reads env vars, no other state. Three
branches, one per backend, each isolated in its own private helper:

```python
# daily_briefing/models.py
import os
from google.adk.models.lite_llm import LiteLlm


def make_model():
    backend = os.getenv("BACKEND", "gemini").lower()
    if backend == "ollama":
        return _ollama()
    if backend == "github":
        return _github_models()
    return _gemini()


def _gemini():
    return os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


def _ollama():
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    return LiteLlm(model=f"ollama_chat/{model}")


def _github_models():
    # LiteLLM's "github/" provider hits https://models.github.ai/inference,
    # GitHub's official OpenAI-compatible endpoint. Auth via GITHUB_API_KEY
    # (a PAT with `models:read` scope). LiteLLM strips company prefixes —
    # pass the bare model name (e.g. "gpt-4.1"), not "openai/gpt-4.1".
    model = os.getenv("GITHUB_MODEL", "gpt-4.1")
    return LiteLlm(model=f"github/{model}")
```

`agent.py` becomes a one-line call: `model=make_model()` inside `make_agent()`.
Existing smoke tests and the bot entry points stay untouched.

### Files modified

| File | Change |
|---|---|
| `daily_briefing/models.py` | **New.** Module above. |
| `daily_briefing/agent.py` | Replace the inline BACKEND switch (lines 19-24) with `from .models import make_model` + `model=make_model()`. |
| `daily_briefing/.env.example` | Add `BACKEND=github` as a documented option; add `GITHUB_API_KEY` and `GITHUB_MODEL` (default `gpt-4.1`) with a comment pointing to https://github.com/settings/tokens for the PAT. |
| `CLAUDE.md` | Append `BACKEND=github`, `GITHUB_API_KEY`, `GITHUB_MODEL` rows to the env-var table. |
| `docs/github-pages/setup.html` | Same edit as `CLAUDE.md`, in the env-vars table (per the docs-sync rule in `CLAUDE.md`). |
| `docs/architecture/daily-briefing-design.md` | Short paragraph wherever BACKEND is described today, noting the module split and the third backend. |
| `requirements.txt` | If `google-adk[extensions]` does not already pin a recent enough `litellm` to include the `github/` provider, add an explicit `litellm>=1.55.0`. Verify before adding. |

### Env vars (added)

- `BACKEND=github` — new accepted value.
- `GITHUB_API_KEY` — GitHub PAT with `models:read` scope. Fine-grained PAT,
  scope = `Models: read`, no repository access required. LiteLLM reads this
  env var name automatically for the `github/*` provider.
- `GITHUB_MODEL` — default `gpt-4.1` (see **Model selection** below for the
  reasoning). Other values per the GitHub Models catalog at
  https://github.com/marketplace/models. LiteLLM strips company prefixes, so
  use the bare name (`gpt-4.1`, not `openai/gpt-4.1`).

## Model selection (Copilot Pro)

The maintainer has a GitHub Copilot **Pro** subscription. Pro grants 1,500
AI credits per month (1,000 base + 500 flex; 1 credit = $0.01). Many models
draw 0 credits on paid plans — those are the right default for an automated
bot.

Tier ladder, cheapest first, sourced from
https://docs.github.com/en/copilot/concepts/billing/copilot-requests
(verified at plan time; GitHub adjusts this list periodically):

| Model | Multiplier (paid plans) | Notes |
|---|---|---|
| `gpt-4.1` | **0x — free** | **Default choice.** Newer than GPT-4o, OpenAI tool-use shape, no credit draw. |
| `gpt-5-mini` | **0x — free** | Strong fallback if `gpt-4.1` rate-limits or quality regresses on tool calls. |
| `gpt-4o` | **0x — free** | Older OpenAI option, also free; keep as last-resort 0x fallback. |
| `gpt-5.4-nano` | 0.25x | ~6,000 requests/month from the Pro allowance. |
| `claude-haiku-4.5` / `gpt-5.4-mini` / `gemini-3-flash` | 0.33x | ~4,500 requests/month from the Pro allowance. |
| `claude-sonnet-4.6` / `gemini-2.5-pro` / `gpt-5.4` | 1x | 1,500 requests/month from the Pro allowance. |
| `claude-opus-4.6` | 3x | 500 requests/month — overkill for the briefing. |
| `gpt-5.5` | 7.5x | ~200 requests/month — do not use as the default. |

For the daily-briefing workload — one scheduled briefing per day plus
ad-hoc Discord conversation — well under 1,000 requests/month even at
the upper bound. **`gpt-4.1` is the right default**: free for any
volume on Pro, modern enough that `instruction.md` won't need heavy
retuning, and supports tool calling for the briefing's API tools.

Document the tier ladder as a short comment block above `GITHUB_MODEL`
in `.env.example` so the choice is reversible without re-reading this
plan.

Rate-limit reminder: 0x means no AI-credit draw, **not** unlimited
throughput. The per-minute and per-day caps on the GitHub Models
endpoint (`models.github.ai`) still apply, and those scale with
subscription tier per the rate-limit table in the GitHub Models docs
(see References below). The briefing's request volume sits well under
the published Pro caps.

## Local dev verification

1. Create a fine-grained PAT at https://github.com/settings/tokens with
   `Models: read`. Drop it in `daily_briefing/.env` as `GITHUB_API_KEY`.
2. Set `BACKEND=github`, `GITHUB_MODEL=gpt-4.1`.
3. Run `python3 daily_briefing/smoke_tests/test_agent.py` — confirm the
   digest prints. (If LiteLLM returns 401 the PAT is wrong; if 403 the
   scope is missing.)
4. Run `python3 -m daily_briefing.discord_bot` and trigger a briefing in the
   channel; confirm round-trip.
5. Flip `BACKEND=gemini` and confirm nothing regressed.

## K3s / production deployment

Simpler than an OAuth device-flow approach would be — the PAT is just another
secret.

1. Add the PAT to Infisical as `daily-briefing/github-api-key`.
2. When the bot's deployment manifest is added to `k3s-homelab/` (tracked
   separately by [`docs/plans/plan-adk-k8s-deployment.md`](plan-adk-k8s-deployment.md)
   — no daily-briefing app dir exists in `k3s-homelab/` yet), include an
   `ExternalSecret` from the `infisical` `ClusterSecretStore` (pattern
   matches `k3s-homelab/infrastructure/controllers/cert-manager/external-secret.yaml`)
   projecting `github-api-key` into a regular `Secret`.
3. In the `Deployment`, set env from that secret:
   - `BACKEND=github` (env literal)
   - `GITHUB_MODEL=gpt-4.1` (env literal)
   - `GITHUB_API_KEY` (from secret)
4. No volume mounts, no init container, no token rotation: PATs rotate only
   when the user chooses to rotate them.

## Caveats

- **Rate limits, not infinite usage.** GitHub Models still rate-limits per
  minute and per day. The numbers are higher for paid Copilot tiers but the
  free tier is modest. Confirm the actual Copilot subscription level matches
  expectations before assuming the quota issue is fully solved.
- **`gpt-4.1` behaves differently from Gemini Flash-Lite.** Different
  prompt sensitivities, tool-call shape, and latency profile. `gpt-4.1`
  *is* free for the maintainer's Pro plan (0x credit draw — see Model
  selection above), so the relevant cost is engineering, not dollars:
  `instruction.md` was tuned for Gemini, so watch for first-call
  regressions in tool-use behaviour and edit the prompt if needed.
- **`github_copilot/*` (the unofficial VS Code path) is intentionally not
  used.** If we later want it as a backup, it can be added as a fourth
  backend (`BACKEND=copilot`) in `models.py` without further refactoring —
  but it carries account-suspension risk and should stay off the documented
  default path.

## References

Sources for every "official API" / "officially supported" claim above:

1. **GitHub Models is GitHub's official inference platform, with rate-limit
   tiers tied to Copilot subscription level** —
   https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models
   (rate-limit table distinguishes Copilot Free / Pro / Business / Enterprise).
2. **REST API base URL, path, OpenAI-compatible request schema, PAT
   `models:read` scope** — https://docs.github.com/en/rest/models/inference
   (`POST https://models.github.ai/inference/chat/completions`; headers
   `Authorization: Bearer <TOKEN>`, `Accept: application/vnd.github+json`,
   `X-GitHub-Api-Version: 2026-03-10`; body is OpenAI chat-completions shape).
3. **LiteLLM `github/*` provider — the path used in this plan** —
   https://docs.litellm.ai/docs/providers/github (model prefix
   `github/<any-model-on-github>`; auth via `GITHUB_API_KEY`; company
   prefixes like `meta/` or `openai/` are stripped).
4. **LiteLLM `github_copilot/*` provider — the unofficial path
   intentionally NOT used** — https://docs.litellm.ai/docs/providers/github_copilot
   (OAuth device flow against the same internal endpoint VS Code Copilot
   uses; LiteLLM injects headers "simulating VSCode" — not a sanctioned
   third-party usage path).
5. **GitHub Models catalog for verifying exact model identifiers at
   implementation time** — https://github.com/marketplace/models.
6. **PAT creation** — https://github.com/settings/tokens (fine-grained PAT,
   scope: `Models: read`, no repository access required).
7. **Copilot Pro usage-based billing** — 1,500 AI credits/month (1,000 base
   + 500 flex; 1 credit = $0.01) —
   https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-individuals
8. **Per-model multipliers (which models are 0x / 0.25x / 0.33x / 1x /
   3x / 7.5x on paid plans)** —
   https://docs.github.com/en/copilot/concepts/billing/copilot-requests
