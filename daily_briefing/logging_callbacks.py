"""ADK callbacks that log model requests/responses and tool invocations.

Wired in :func:`daily_briefing.agent.make_agent` so every LLM round-trip and
every tool call shows up as a single, scannable line in the logs:

    model_request: turn=3 — "Fetch weather for Grand Rapids…"
    tool_call: get_weather(location='Grand Rapids, MI')
    tool_result: get_weather in 0.42s → "Today: 65°F sunny…"
    model_response: "Good morning! Here's your…"

We deliberately don't dump full request/response JSON — the goal is the
prompt-and-reply story plus a tool-call trail, not a tcpdump.

All four callbacks are defensive: any exception in the logging path is
caught and logged via :func:`logger.exception`, never propagated.
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
            "model_request: turn=%d — %s",
            turns,
            _summarize_latest_turn(llm_request),
        )
    except Exception:
        logger.exception("log_before_model failed")
    return None


def log_after_model(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> None:
    """Log the LLM's reply text + any tool calls it requested."""
    try:
        # Skip streaming partials so we don't spam one line per token.
        if getattr(llm_response, "partial", None):
            return None

        text = ""
        content = getattr(llm_response, "content", None)
        if content and content.parts:
            text = "".join(p.text for p in content.parts if getattr(p, "text", None))

        try:
            tool_calls = llm_response.get_function_calls()
        except Exception:
            tool_calls = []

        if text:
            logger.info("model_response: %r", preview(text, _PREVIEW_CHARS))
        if tool_calls:
            names = ", ".join(fc.name for fc in tool_calls)
            logger.info("model_response: requested %d tool call(s) — %s", len(tool_calls), names)
        if not text and not tool_calls:
            finish = getattr(llm_response, "finish_reason", None)
            logger.info("model_response: (empty) finish=%s", finish)
    except Exception:
        logger.exception("log_after_model failed")
    return None


def _format_args(args: dict[str, Any]) -> str:
    """Compact one-line ``key=value`` rendering for a tool args dict."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        parts.append(f"{k}={preview(repr(v), _PREVIEW_CHARS)}")
    return ", ".join(parts)


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

        logger.info("tool_call: %s(%s)", tool.name, _format_args(args))
    except Exception:
        logger.exception("log_before_tool failed")
    return None


def log_after_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict,
) -> None:
    """Log tool result as one line: ``tool_result: name in N.NNs → "…"``."""
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

        body_preview = preview(str(tool_response), _PREVIEW_CHARS)
        if elapsed is None:
            logger.info("tool_result: %s → %r", tool.name, body_preview)
        else:
            logger.info(
                "tool_result: %s in %.2fs → %r", tool.name, elapsed, body_preview
            )
    except Exception:
        logger.exception("log_after_tool failed")
    return None
