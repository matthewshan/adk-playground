"""ADK callbacks that log model requests/responses and tool invocations.

Wired in :func:`daily_briefing.agent.make_agent` so every agent invocation,
LLM round-trip, and tool call shows up as a single, scannable line. Each line
carries a correlation tag — ``[<inv> u=<user>]`` — so the interleaved logs of
concurrent Discord sessions can be untangled:

    [a1b2c3d4 u=scheduler] agent_start: 'Fetch weather for Grand Rapids…'
    [a1b2c3d4 u=scheduler] model_request: turn=1 — role=user 'Fetch weather…'
    [a1b2c3d4 u=scheduler] model_response: requested 2 tool call(s) — get_weather, get_news
    [a1b2c3d4 u=scheduler] tool_call: get_weather()
    [a1b2c3d4 u=scheduler] tool_result: get_weather in 0.42s → 'Now: 65°F…'
    [a1b2c3d4 u=scheduler] model_usage: prompt=1840 output=210 total=2050
    [a1b2c3d4 u=scheduler] agent_done: in 4.1s — 2 tool call(s), ~4100 tokens

We deliberately don't dump full request/response JSON — the goal is the
prompt-and-reply story plus a tool-call trail, not a tcpdump. Tool calls that
return an error-shaped result are logged at WARNING so upstream failures (a
weather server error, a missing API key) surface without grepping.

All callbacks are defensive: any exception in the logging path is caught and
logged via :func:`logger.exception`, never propagated.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from daily_briefing.log_config import preview

logger = logging.getLogger(__name__)

# Cap each previewed value/text used in log lines.
_PREVIEW_CHARS = 200
# Per-session scratchpad key for tool start times → tool_result latencies.
_START_KEY = "_log_tool_start"
# Per-session scratchpad key for the current invocation's running tallies.
_INV_KEY = "_log_inv"

# Substrings that mark an error-shaped tool result (tools degrade to a plain
# string / JSON note rather than raising, so failures are easy to miss in logs).
_ERROR_MARKERS = (
    "unavailable:",
    "error fetching",
    "not found on espn",
    "bad service-account",
    "bad start_date",
    '"error"',
    "no game currently in progress",
)


# ---------------------------------------------------------------------------
# Correlation tag + per-invocation scratchpad helpers
# ---------------------------------------------------------------------------


def _ctx_tag(ctx: CallbackContext | ToolContext) -> str:
    """Short ``[<inv> u=<user>]`` correlation tag for a callback context."""
    try:
        inv = (getattr(ctx, "invocation_id", "") or "")[-8:] or "?"
        uid = getattr(ctx, "user_id", "") or ""
        return f"[{inv} u={uid}]" if uid else f"[{inv}]"
    except Exception:
        return "[?]"


def _inv_state(ctx: CallbackContext | ToolContext) -> dict | None:
    """Return the current invocation's tally dict from session state, or None."""
    try:
        return ctx.state.get(_INV_KEY)  # type: ignore[union-attr]
    except Exception:
        return None


def _save_inv_state(ctx: CallbackContext | ToolContext, data: dict) -> None:
    try:
        ctx.state[_INV_KEY] = data  # type: ignore[union-attr]
    except Exception:
        pass


def _content_preview(content: Any) -> str:
    """One-line preview of a types.Content's text parts."""
    parts = getattr(content, "parts", None) or []
    text = " ".join(p.text for p in parts if getattr(p, "text", None))
    return preview(text, _PREVIEW_CHARS) if text else "(no text)"


# ---------------------------------------------------------------------------
# Agent-level callbacks (per-invocation bracket + summary)
# ---------------------------------------------------------------------------


def log_before_agent(callback_context: CallbackContext) -> None:
    """Open the per-invocation bracket and reset its running tallies."""
    try:
        _save_inv_state(
            callback_context,
            {"start": time.monotonic(), "tool_calls": 0, "tokens": 0},
        )
        logger.info(
            "%s agent_start: %s",
            _ctx_tag(callback_context),
            _content_preview(getattr(callback_context, "user_content", None)),
        )
    except Exception:
        logger.exception("log_before_agent failed")
    return None


def log_after_agent(callback_context: CallbackContext) -> None:
    """Close the bracket with a one-line summary: latency, tool count, tokens."""
    try:
        inv = _inv_state(callback_context) or {}
        start = inv.get("start")
        elapsed = f"{time.monotonic() - start:.1f}s" if start else "?"
        logger.info(
            "%s agent_done: in %s — %d tool call(s), ~%d tokens",
            _ctx_tag(callback_context),
            elapsed,
            inv.get("tool_calls", 0),
            inv.get("tokens", 0),
        )
    except Exception:
        logger.exception("log_after_agent failed")
    return None


# ---------------------------------------------------------------------------
# Model callbacks
# ---------------------------------------------------------------------------


def _summarize_latest_turn(llm_request: LlmRequest) -> str:
    """One-line preview of the most recent content sent to the LLM."""
    contents = llm_request.contents or []
    if not contents:
        return "(empty)"
    last = contents[-1]
    role = getattr(last, "role", "?")
    bits: list[str] = []
    for part in last.parts or []:
        if getattr(part, "text", None):
            bits.append(part.text)
        elif getattr(part, "function_response", None) is not None:
            fr = part.function_response
            bits.append(f"<{getattr(fr, 'name', '?')} result>")
        elif getattr(part, "function_call", None) is not None:
            fc = part.function_call
            bits.append(f"<call {getattr(fc, 'name', '?')}>")
    text = " ".join(bits) if bits else "(no text)"
    return f"role={role} {preview(text, _PREVIEW_CHARS)!r}"


def log_before_model(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """Log the prompt being sent to the LLM (most recent turn only)."""
    try:
        turns = len(llm_request.contents or [])
        logger.info(
            "%s model_request: turn=%d — %s",
            _ctx_tag(callback_context),
            turns,
            _summarize_latest_turn(llm_request),
        )
    except Exception:
        logger.exception("log_before_model failed")
    return None


def log_after_model(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> None:
    """Log the LLM's reply text, any tool calls it requested, and token usage."""
    try:
        # Skip streaming partials so we don't spam one line per token.
        if getattr(llm_response, "partial", None):
            return None

        tag = _ctx_tag(callback_context)

        text = ""
        content = getattr(llm_response, "content", None)
        if content and content.parts:
            text = "".join(p.text for p in content.parts if getattr(p, "text", None))

        try:
            tool_calls = llm_response.get_function_calls()
        except Exception:
            tool_calls = []

        if text:
            logger.info("%s model_response: %r", tag, preview(text, _PREVIEW_CHARS))
        if tool_calls:
            names = ", ".join(fc.name for fc in tool_calls)
            logger.info(
                "%s model_response: requested %d tool call(s) — %s",
                tag,
                len(tool_calls),
                names,
            )
        if not text and not tool_calls:
            finish = getattr(llm_response, "finish_reason", None)
            logger.info("%s model_response: (empty) finish=%s", tag, finish)

        _log_usage(callback_context, tag, llm_response)
    except Exception:
        logger.exception("log_after_model failed")
    return None


def _log_usage(
    callback_context: CallbackContext, tag: str, llm_response: LlmResponse
) -> None:
    """Log per-call token usage and accumulate the invocation total."""
    um = getattr(llm_response, "usage_metadata", None)
    if um is None:
        return  # some LiteLLM backends omit usage metadata
    prompt = getattr(um, "prompt_token_count", None)
    output = getattr(um, "candidates_token_count", None)
    total = getattr(um, "total_token_count", None)
    logger.info(
        "%s model_usage: prompt=%s output=%s total=%s", tag, prompt, output, total
    )
    if isinstance(total, int):
        inv = _inv_state(callback_context)
        if inv is not None:
            inv["tokens"] = inv.get("tokens", 0) + total
            _save_inv_state(callback_context, inv)


# ---------------------------------------------------------------------------
# Tool callbacks
# ---------------------------------------------------------------------------


def _format_args(args: dict[str, Any]) -> str:
    """Compact one-line ``key=value`` rendering for a tool args dict."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        parts.append(f"{k}={preview(repr(v), _PREVIEW_CHARS)}")
    return ", ".join(parts)


def _looks_like_error(tool_response: Any) -> bool:
    """True when a tool's (string/JSON) result looks like a degraded failure."""
    blob = str(tool_response).lower()
    return any(marker in blob for marker in _ERROR_MARKERS)


def log_before_tool(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> None:
    """Log a tool invocation as one line: ``tool_call: name(k=v, …)``."""
    try:
        try:
            state = tool_context.state
            starts = state.get(_START_KEY) or {}
            starts[tool.name] = time.monotonic()
            state[_START_KEY] = starts
        except Exception:
            pass  # latency just stays unknown

        inv = _inv_state(tool_context)
        if inv is not None:
            inv["tool_calls"] = inv.get("tool_calls", 0) + 1
            _save_inv_state(tool_context, inv)

        logger.info(
            "%s tool_call: %s(%s)",
            _ctx_tag(tool_context),
            tool.name,
            _format_args(args),
        )
    except Exception:
        logger.exception("log_before_tool failed")
    return None


def log_after_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict,
) -> None:
    """Log tool result as one line; error-shaped results log at WARNING."""
    try:
        elapsed = None
        try:
            state = tool_context.state
            starts = state.get(_START_KEY) or {}
            start = starts.pop(tool.name, None)
            if start is not None:
                elapsed = time.monotonic() - start
                state[_START_KEY] = starts
        except Exception:
            pass

        tag = _ctx_tag(tool_context)
        body_preview = preview(str(tool_response), _PREVIEW_CHARS)
        level = logging.WARNING if _looks_like_error(tool_response) else logging.INFO
        took = "" if elapsed is None else f" in {elapsed:.2f}s"
        logger.log(level, "%s tool_result: %s%s → %r", tag, tool.name, took, body_preview)
    except Exception:
        logger.exception("log_after_tool failed")
    return None
