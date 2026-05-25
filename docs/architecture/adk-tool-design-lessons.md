# ADK Tool Design — Lessons Learned

Patterns and pitfalls discovered while building and debugging the daily briefing
agent. Apply these rules whenever writing or modifying ADK tool functions.

---

## 1. Complex type annotations break Gemini function calling

**Problem:** ADK's experimental JSON schema generator
(`FeatureName.JSON_SCHEMA_FOR_FUNC_DECL`) converts Python type annotations into
the JSON Schema that the Gemini API uses for function declarations. When a
parameter uses a custom dataclass, a union with `None`, or nested generics, the
generator produces schemas with `$defs`, `$ref`, and `anyOf` — features the
Gemini function-calling API does not support. The tool call silently fails and
the LLM hallucinates a failure message (e.g. "Failed to fetch scores") rather
than raising an error you can catch.

**Symptom:** Tool output is missing from the briefing even though the same
function works fine when called directly from a smoke test.

**Root cause example:**
```python
# BAD — generates $defs / $ref / anyOf, Gemini rejects it silently
def get_sports_scores(teams: list[TrackedTeam] | None = None) -> str: ...
```

Generated schema (broken):
```json
{
  "$defs": { "TrackedTeam": { "properties": { ... } } },
  "properties": {
    "teams": { "anyOf": [{ "items": { "$ref": "#/$defs/TrackedTeam" }, "type": "array" }, { "type": "null" }] }
  }
}
```

**Fix:** Remove the type annotation from parameters that the LLM should not
fill, or that use complex types. A bare `param=None` generates no schema entry
or a trivially simple one that the API accepts:
```python
# GOOD — no $defs, no $ref, no anyOf
def get_sports_scores(teams=None) -> str: ...
```

**How to verify:** Inspect the generated declaration before shipping:
```python
from google.adk.tools.function_tool import FunctionTool
ft = FunctionTool(your_tool_func)
print(ft._get_declaration().parameters_json_schema)
# Should be None or a flat object with only primitive-typed properties
```

---

## 2. LLMs fill optional parameters even when they shouldn't

**Problem:** Even with an untyped `teams=None` parameter, smarter models
(`gemini-3.1-flash-lite`, `qwen3:8b`) see the parameter name in the schema and
decide to pass a value — typically a list of strings like
`["Detroit Lions", "Toronto Blue Jays"]` instead of the expected dataclass
objects. This causes `AttributeError: 'str' object has no attribute 'league_label'`
at runtime.

**Fix:** Validate incoming args at the top of every tool function and fall back
to safe defaults when the type is wrong. Do this before touching any argument
fields:

```python
def get_sports_scores(teams=None) -> str:
    # Guard: fall back to defaults if called with no args OR if the LLM
    # passed strings or other non-TrackedTeam values.
    if not teams or not all(isinstance(t, (TrackedTeam, dict)) for t in teams):
        teams = _DEFAULT_TEAMS
    ...
```

**General rule:** Any tool parameter that has a meaningful default should guard
against unexpected LLM-supplied values before using them.

---

## 3. Gemini API — free-tier model comparison (verified May 2026)

All limits below are free-tier (no billing). Check your actual project limits at
[aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit) —
Google adjusts these frequently and per-project limits may differ from published
figures.

| Model ID | RPM | RPD | ADK tool calling | Notes |
|---|---|---|---|---|
| `gemini-2.5-flash` | 5–10 | ~20 | ✅ | Hits daily limit quickly |
| `gemini-2.5-flash-lite` | 10–15 | 1,000 | ✅ | Good daily default |
| `gemini-3.1-flash-lite` | 15 | 500 | ✅ | Solid alternative |
| `gemma-4-26b-a4b-it` | 15 | 1,500 | ❌ | **Does not work** with ADK tool/function calling |
| `gemma-4-31b-it` | 15 | 1,500 | ❌ | **Does not work** with ADK tool/function calling |

> **Gemma 4 note:** Despite the generous quota, Gemma 4 models served through
> the Gemini API do not support function calling in ADK. The agent crashes at
> runtime. Use `gemini-3.1-flash-lite` instead if you need a higher RPD ceiling.

Set the model in `daily_briefing/.env`:
```env
GEMINI_MODEL=gemini-3.1-flash-lite   # 500 RPD, confirmed tool calling
```

---

## 4. Ollama as a rate-limit-free local backend

Set these in `.env` to bypass all Gemini quotas during development:

```env
BACKEND=ollama
OLLAMA_API_BASE=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
```

### Model recommendations for local inference (RTX 3070 / 8 GB VRAM)

| Model | VRAM | Tool calling | Notes |
|---|---|---|---|
| `qwen2.5:7b` ⭐ | ~4.5 GB | ✅ excellent | **Recommended.** Fast, follows instructions without asking for confirmation, no thinking overhead. Already the default in `.env.example`. |
| `qwen3:8b` | ~5.5 GB | ✅ works | Has a built-in **thinking/reasoning mode** that is on by default — model narrates its entire decision process before responding, producing extremely verbose output unsuitable for a briefing agent. Can be disabled with `/no_think` but that requires patching the system prompt. |
| `llama3.1:8b` | ~4.9 GB | ⚠️ poor | Asks for user confirmation mid-task instead of just executing tools. |
| `qwen3.6` (36B) | 23 GB | — | Does **not** fit in 8 GB VRAM. |

`qwen2.5:7b` is the recommended local model. Pull it once:
```bash
ollama pull qwen2.5:7b
```

> **Qwen3 thinking mode:** If you do use `qwen3:8b`, be aware it behaves like
> an o1-style reasoning model — it prints a long internal monologue before
> every response. For a quick daily briefing this is counterproductive. Stick
> with `qwen2.5:7b` for local development.

---

## 5. Windows UTF-8 encoding in smoke tests

The daily briefing output contains Unicode characters (◀ standings marker, ✓/✗
pass/fail symbols, emoji). Windows defaults to the `cp1252` codec, which cannot
encode these and raises `UnicodeEncodeError` when the test prints to stdout.

**Fix:** Add this block near the top of every smoke test script, before any
print statements:
```python
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

This is already present in `smoke_tests/test_agent.py` and
`smoke_tests/test_sports.py`.

---

## Related

- [daily-briefing-design.md](daily-briefing-design.md) — module layout and data flow
- [ADK function tool source](https://github.com/google/adk-python) — `google/adk/tools/function_tool.py`
- [Ollama tool calling docs](https://docs.ollama.com/capabilities/tool-calling)
