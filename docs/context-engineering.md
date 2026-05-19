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
