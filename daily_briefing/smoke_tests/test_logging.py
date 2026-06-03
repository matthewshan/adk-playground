"""Logging-callback unit tests.

Validates the ADK callbacks in :mod:`daily_briefing.logging_callbacks` without
a live agent: correlation tags, token accounting, the per-invocation summary,
and the WARNING level for error-shaped tool results.
"""

from __future__ import annotations

import logging
import sys
import types
import unittest
from pathlib import Path

# Allow running this file directly from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from daily_briefing import logging_callbacks as lc


class _Ctx:
    """Minimal stand-in for an ADK CallbackContext / ToolContext."""

    def __init__(self, invocation_id: str = "e-abcd1234ef56", user_id: str = "scheduler"):
        self.invocation_id = invocation_id
        self.user_id = user_id
        self.state: dict = {}
        self.user_content = types.SimpleNamespace(
            parts=[types.SimpleNamespace(text="Write the morning digest")]
        )


class _Tool:
    def __init__(self, name: str):
        self.name = name


class LoggingCallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records: list[tuple[str, str]] = []

        class _Cap(logging.Handler):
            def emit(_self, record: logging.LogRecord) -> None:
                self.records.append((record.levelname, record.getMessage()))

        self.handler = _Cap()
        lc.logger.addHandler(self.handler)
        lc.logger.setLevel(logging.INFO)

    def tearDown(self) -> None:
        lc.logger.removeHandler(self.handler)

    def _messages(self) -> str:
        return "\n".join(m for _, m in self.records)

    def test_correlation_tag_uses_short_invocation_and_user(self) -> None:
        ctx = _Ctx()
        lc.log_before_agent(ctx)
        # invocation_id is "e-abcd1234ef56"; tag uses the last 8 chars.
        self.assertIn("[1234ef56 u=scheduler]", self._messages())

    def test_error_shaped_tool_result_logs_warning(self) -> None:
        ctx = _Ctx()
        lc.log_before_agent(ctx)
        lc.log_before_tool(_Tool("get_weather"), {}, ctx)
        lc.log_after_tool(_Tool("get_weather"), {}, ctx, {"result": "Now: 65F sunny"})
        lc.log_before_tool(_Tool("get_news"), {}, ctx)
        lc.log_after_tool(
            _Tool("get_news"), {}, ctx, {"result": "News unavailable: HTTPError 500"}
        )
        levels = {name: lvl for lvl, name in self.records if "tool_result" in name}
        self.assertTrue(any(lvl == "INFO" and "get_weather" in m for lvl, m in self.records))
        self.assertTrue(any(lvl == "WARNING" and "get_news" in m for lvl, m in self.records))

    def test_summary_tallies_tool_calls_and_tokens(self) -> None:
        ctx = _Ctx()
        lc.log_before_agent(ctx)
        lc.log_before_tool(_Tool("get_weather"), {}, ctx)
        lc.log_after_tool(_Tool("get_weather"), {}, ctx, {"result": "ok"})
        lc.log_before_tool(_Tool("get_news"), {}, ctx)
        lc.log_after_tool(_Tool("get_news"), {}, ctx, {"result": "ok"})

        usage = types.SimpleNamespace(
            prompt_token_count=1840, candidates_token_count=210, total_token_count=2050
        )
        resp = types.SimpleNamespace(
            partial=False, content=None, usage_metadata=usage, finish_reason="STOP"
        )
        resp.get_function_calls = lambda: []
        lc.log_after_model(ctx, resp)
        lc.log_after_agent(ctx)

        msgs = self._messages()
        self.assertIn("model_usage: prompt=1840 output=210 total=2050", msgs)
        self.assertTrue(
            any("2 tool call(s)" in m and "~2050 tokens" in m for _, m in self.records)
        )

    def test_callbacks_never_raise_on_malformed_context(self) -> None:
        # A context missing the expected attributes must not break a turn.
        bad = types.SimpleNamespace()
        lc.log_before_agent(bad)  # type: ignore[arg-type]
        lc.log_after_agent(bad)  # type: ignore[arg-type]
        # No assertion needed: the test passes if nothing propagated.


if __name__ == "__main__":
    unittest.main(verbosity=2)
