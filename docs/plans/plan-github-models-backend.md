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

The maintainer has a GitHub Copilot **Pro** subscription. The billing
structure for Pro is changing on **June 1, 2026**, and implementation of
this plan straddles that cutover (today is 2026-05-28). The model
recommendation below holds in both eras — only the explanation differs.

**Recommended default: `gpt-4.1`.**

### Why `gpt-4.1`

| Era | Billing for `gpt-4.1` on Copilot Pro |
|---|---|
| Current (through 2026-05-31) | One of the three "included models" with **unlimited chat** — does not draw against the premium-request allowance. The other two are `gpt-4o` and `gpt-5-mini`. |
| Post-cutover (from 2026-06-01) | One of the **0x AI-credit** models — does not draw against the 1,500-credit monthly allowance (1,000 base + 500 flex; 1 credit = $0.01). The other two are still `gpt-4o` and `gpt-5-mini`. |

So `gpt-4.1` is effectively free on Pro in both eras for any volume the
daily-briefing workload will produce (one scheduled briefing per day plus
ad-hoc Discord conversation — easily under 1,000 requests/month). It is
also newer than `gpt-4o`, supports tool calling, and uses the OpenAI
chat-completions shape that the ADK `LiteLlm` wrapper already speaks well.

### Fallback ladder (if `gpt-4.1` rate-limits)

Rate-limit reminder: "0x AI credits" / "unlimited chat" mean no cost
draw — they do **not** mean unbounded throughput. The per-minute and
per-day caps on `models.github.ai` still apply and scale with the
subscription tier. The published Pro caps comfortably cover the
briefing's workload, but if they ever bite, fall back in this order:

1. `gpt-5-mini` (included today / 0x post-cutover) — still free.
2. `gpt-4o` (included today / 0x post-cutover) — still free.
3. After June 1, 2026: paid-but-cheap options — `gpt-5.4-nano` at 0.25x
   (~6,000 req/mo from the Pro credit pool), then the 0.33x tier
   (`claude-haiku-4.5`, `gemini-3-flash`, `gpt-5.4-mini` — ~4,500
   req/mo).
4. Pre-June-1 alternative if the included models rate-limit: a 1x
   premium model (e.g. `claude-sonnet-4.6`, `gemini-2.5-pro`) charged
   against the Pro premium-request allowance.

Document the fallback ladder as a short comment block above
`GITHUB_MODEL` in `.env.example` so the next provider switch is reversible
without re-reading this plan.

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

## Other providers considered

GitHub Models is the only consumer subscription of the major providers that
also opens up its rate-limited inference API to subscribers. For context, if
the maintainer later picks up an OpenAI or Google subscription, **neither
gives a Copilot-style path** — they would need separate API billing:

| Provider | Consumer subscription | Does it grant API access? | What the API path actually is |
|---|---|---|---|
| OpenAI | ChatGPT Plus / Pro / Team | **No.** Subscription covers the chat web/mobile app only. | Open an OpenAI Platform account at `platform.openai.com`, prepay credits, get an API key. LiteLLM provider prefix: `openai/<model>`. |
| Google | Google AI Pro / Ultra (fka Gemini Advanced) | **No.** Subscription covers the Gemini chat app, NotebookLM Pro, etc. Does **not** raise Gemini API quotas. | Attach a Cloud billing account to the Google Cloud / AI Studio project that owns `GEMINI_API_KEY`. Same model strings as today, no code change — only billing flips from free tier to pay-as-you-go. |
| GitHub | Copilot Pro / Business / Enterprise | **Yes.** Rate-limit tiers on `models.github.ai` scale with subscription level. | The path used by this plan: LiteLLM `github/<model>`. |

Practical implication for the current Gemini Studio quota pain: a Google
AI Pro subscription would not relieve it; turning on Cloud billing on the
existing `GEMINI_API_KEY`'s project would. Likewise, ChatGPT Plus would
not give the bot any OpenAI API access — only a paid OpenAI Platform
account would.

If either of those gets set up later, both can slot into `models.py`
alongside the GitHub branch with one new `_provider()` helper each — the
module structure introduced by this plan makes that addition a 5-line
change, not a refactor.

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
7. **Current Copilot Pro premium-request rules (in effect through
   2026-05-31)** — confirms `gpt-4.1`, `gpt-4o`, and `gpt-5-mini` are the
   "included models" with unlimited chat on paid plans; everything else
   draws against the premium-request allowance with multipliers (Haiku
   0.33x, Sonnet 1x, Opus 3x, etc.) —
   https://docs.github.com/en/copilot/managing-copilot/monitoring-usage-and-entitlements/about-premium-requests
8. **Upcoming Copilot Pro AI-credits billing (effective 2026-06-01)** —
   1,500 AI credits/month (1,000 base + 500 flex; 1 credit = $0.01) —
   https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-individuals
9. **Post-cutover per-model multipliers (which models are 0x / 0.25x /
   0.33x / 1x / 3x / 7.5x on paid plans from 2026-06-01)** —
   https://docs.github.com/en/copilot/concepts/billing/copilot-requests
