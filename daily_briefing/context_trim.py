"""Trim an LLM request to fit a backend's per-request token cap.

GitHub Models' free tier rejects request bodies over 8000 tokens. The bot's
session history (especially large tool results like sports JSON or web-search
content) grows past that within a few turns, so we cap each request before it
is sent: oversized individual parts are truncated, then the oldest turns are
dropped until the contents fit the budget.

Wired as ``before_model_callback`` only on backends that report a limit
(see ``models.request_token_limit``); a no-op everywhere else.
"""

from __future__ import annotations

import logging

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4  # rough heuristic — good enough for budgeting
# Headroom below the hard cap for the system instruction and tool schemas,
# which also count toward the request body but aren't in `contents`.
_RESERVE_TOKENS = 3500
_MAX_PART_CHARS = 6000  # truncate any single oversized tool result / text part
_TRUNCATED = " …[truncated]"


def _part_text_len(part) -> int:
    """Approximate character length of a part's payload (text / tool call / result)."""
    total = 0
    if getattr(part, "text", None):
        total += len(part.text)
    fc = getattr(part, "function_call", None)
    if fc is not None:
        total += len(str(getattr(fc, "args", "")))
    fr = getattr(part, "function_response", None)
    if fr is not None:
        total += len(str(getattr(fr, "response", "")))
    return total


def _truncate_part(part) -> None:
    """Shrink an oversized part in place: text directly, tool results value-by-value."""
    if getattr(part, "text", None) and len(part.text) > _MAX_PART_CHARS:
        part.text = part.text[:_MAX_PART_CHARS] + _TRUNCATED
    fr = getattr(part, "function_response", None)
    resp = getattr(fr, "response", None) if fr is not None else None
    if isinstance(resp, dict):
        for key, value in resp.items():
            if isinstance(value, str) and len(value) > _MAX_PART_CHARS:
                resp[key] = value[:_MAX_PART_CHARS] + _TRUNCATED


def make_trimmer(limit: int):
    """Return a before_model_callback that keeps request `contents` under *limit* tokens."""
    budget = max(limit - _RESERVE_TOKENS, 1000)

    def trim_request(callback_context: CallbackContext, llm_request: LlmRequest):
        try:
            contents = llm_request.contents or []
            for content in contents:
                for part in content.parts or []:
                    _truncate_part(part)

            def total() -> int:
                chars = sum(
                    _part_text_len(p) for c in contents for p in (c.parts or [])
                )
                return chars // _CHARS_PER_TOKEN

            # Drop oldest turns until under budget, but always keep the last one.
            while len(contents) > 1 and total() > budget:
                dropped = contents.pop(0)
                logger.debug("context_trim: dropped 1 old turn (role=%s)", getattr(dropped, "role", "?"))

            llm_request.contents = contents
        except Exception:
            # Trimming is best-effort — never let it break a turn.
            logger.exception("context_trim failed; sending request untrimmed")
        return None

    return trim_request
