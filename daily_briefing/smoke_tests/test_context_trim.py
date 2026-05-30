"""Unit tests for context_trim — no network, no agent.

Run: python3 daily_briefing/smoke_tests/test_context_trim.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from google.adk.models.llm_request import LlmRequest  # noqa: E402
from google.genai import types  # noqa: E402

from daily_briefing.context_trim import _MAX_PART_CHARS, make_trimmer  # noqa: E402


def _text_turn(role: str, chars: int) -> types.Content:
    return types.Content(role=role, parts=[types.Part.from_text(text="x" * chars)])


def drops_oldest_turns_over_budget() -> None:
    # 20 turns × 2000 chars = ~10000 tokens, well over the 4500-token budget.
    req = LlmRequest(contents=[_text_turn("user", 2000) for _ in range(20)])
    last = req.contents[-1]
    make_trimmer(8000)(None, req)

    assert len(req.contents) < 20, "expected old turns to be dropped"
    assert req.contents[-1] is last, "most recent turn must be preserved"


def truncates_oversized_part() -> None:
    req = LlmRequest(contents=[_text_turn("user", _MAX_PART_CHARS * 3)])
    make_trimmer(8000)(None, req)

    text = req.contents[0].parts[0].text
    assert text.endswith("…[truncated]"), "oversized part should be truncated"
    assert len(text) <= _MAX_PART_CHARS + 20


def leaves_small_request_untouched() -> None:
    req = LlmRequest(contents=[_text_turn("user", 100), _text_turn("model", 100)])
    make_trimmer(8000)(None, req)
    assert len(req.contents) == 2, "small request must not be trimmed"


def never_drops_below_one_turn() -> None:
    # A single oversized turn can't be dropped (it's the most recent); it's only truncated.
    req = LlmRequest(contents=[_text_turn("user", 100000)])
    make_trimmer(8000)(None, req)
    assert len(req.contents) == 1


if __name__ == "__main__":
    for test in (
        drops_oldest_turns_over_budget,
        truncates_oversized_part,
        leaves_small_request_untouched,
        never_drops_below_one_turn,
    ):
        test()
        print(f"PASS {test.__name__}")
    print("All context_trim tests passed.")
