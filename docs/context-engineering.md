# Context Engineering Notes

This project uses a very small local model. That changes how prompts should be written.

## Constraints

- Tiny models lose track of long instructions quickly.
- They are much worse at tool selection, planning, and recovery.
- Large context windows are not useful here if the model quality is already low.

## Rules for this repo

- Keep the system instruction short and stable.
- Ask for one task per prompt.
- Prefer explicit output constraints like "reply with one sentence" or "return JSON only".
- Avoid multi-step reasoning prompts unless you really need them.
- Keep conversation history short during debugging.

## Good prompt shape

Use this pattern:

1. State the role briefly.
2. State the task in one sentence.
3. State the output format in one sentence.

Example:

```text
You are a concise local test assistant.
Answer the user's question in one sentence.
If the user asks for a fixed string, return that exact string.
```

## What to avoid

- Large few-shot prompts
- Multiple competing rules
- Hidden formatting expectations
- Asking the model to both plan and execute when a direct answer is enough

## Scaling up later

If this smoke test works and you want something more realistic:

1. Move to `qwen2.5:0.5b` first.
2. Add one trivial tool only after plain chat works.
3. Keep a separate smoke test prompt for regression checks.

---

## Tool signature design (ADK)

The LLM generates tool calls as JSON. If your function signature uses complex
Python types, the model will guess the shape incorrectly and the tool will fail.

**Rules:**

- **Use primitive types only in parameters** — `str`, `int`, `bool`, `list[str]`,
  `dict`. Avoid dataclasses, Pydantic models, or custom classes in signatures.
  The model cannot construct them; it will pass plain strings or dicts with
  wrong keys, causing silent failures.

- **Default fixed data inside the tool, not in the prompt** — If the instruction
  hardcodes which teams/cities/topics to fetch, mirror that in the tool as a
  `None`-defaulted parameter. The model should call `get_sports_scores()` with
  no arguments, not `get_sports_scores(teams=[TrackedTeam(...)])`.

- **Validate and fall back defensively** — Assume the LLM may pass something
  invalid even with a correct schema. Check `isinstance` and fall back to
  defaults rather than letting `AttributeError` propagate:

  ```python
  if not teams or not all(isinstance(t, (TrackedTeam, dict)) for t in teams):
      teams = _DEFAULT_TEAMS
  ```

- **Surface errors in return values, not exceptions** — ADK passes tool return
  values back to the model as text. An unhandled exception becomes an opaque
  error message; the model then invents an excuse. Return a string like
  `"Error fetching Lions scores: <reason>"` instead.

**Why it matters for bigger models too:** GPT-4 / Gemini are better at
guessing shapes but still fail on nested custom types. This rule holds
regardless of model size.

---

## Request-size caps (hosted backends)

Some backends reject the request itself, not just produce worse output.
**GitHub Models' free tier caps the gpt-4.1 request body at 8000 input tokens**
(system instruction + tool schemas + the full session `contents`). The bot
re-sends the whole conversation every turn, and large tool results (web-search
snippets, sports JSON) accumulate in history — so even a tiny query like
"what's the weather" can fail once earlier results have piled up.

**Rules:**

- **Know each backend's cap.** `models.request_token_limit()` returns the active
  backend's limit (8000 for `BACKEND=github`, `None` for Gemini/Ollama).
- **Trim per request, not just per session.** `context_trim.make_trimmer()` is
  wired as the agent's `before_model_callback` only on capped backends. It
  truncates any oversized part and drops the oldest turns until `contents` fit a
  budget (`limit − 3500` reserve), always keeping the most recent turn. It's
  best-effort (wrapped in try/except) so it can never break a turn.
- **Bound tool output at the source too.** A tool that can return a lot (e.g.
  `web_search` → Tavily) should cap its own result — `web_search` returns at
  most 3 results with 300-char snippets.

**Limitation:** the one-shot morning digest fetches weather + news + sports +
search in a single turn, so its combined tool results can still exceed 8000 on
`BACKEND=github` — trimming can't help (all the data is in the current turn).
Run the scheduled briefing on Gemini.
