"""
Unit tests for daily_briefing/discord_bot.py — no Discord token required.

Tests pure helper functions and constants, covering:
  - _split_message: short/long messages, newline-preference, edge cases
  - _SCHEDULER_USER_ID: stable string key for the scheduled briefing scope
  - _check_supabase_config: logs a warning when Supabase env vars are absent

Run:
    python daily_briefing/smoke_tests/test_discord_bot.py
"""

import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow running from the repo root or the smoke_tests/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from daily_briefing.discord_bot import (
    _SCHEDULER_USER_ID,
    _check_supabase_config,
    _split_message,
)


class SplitMessageTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # Basic cases
    # ------------------------------------------------------------------

    def test_empty_string_returns_single_empty_chunk(self) -> None:
        result = _split_message("")
        self.assertEqual(result, [""])

    def test_short_message_is_single_chunk(self) -> None:
        result = _split_message("hello world")
        self.assertEqual(result, ["hello world"])

    def test_message_exactly_at_limit_is_single_chunk(self) -> None:
        text = "x" * 2000
        result = _split_message(text, limit=2000)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], text)

    # ------------------------------------------------------------------
    # Multi-chunk splitting
    # ------------------------------------------------------------------

    def test_long_message_without_newlines_is_hard_split(self) -> None:
        text = "x" * 4500
        chunks = _split_message(text, limit=2000)
        # Expect 3 chunks: 2000 + 2000 + 500
        self.assertEqual(len(chunks), 3)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 2000)
        self.assertEqual("".join(chunks), text)

    def test_all_content_preserved_across_chunks(self) -> None:
        text = "a" * 3000 + "b" * 3000
        chunks = _split_message(text, limit=2000)
        self.assertEqual("".join(chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 2000)

    # ------------------------------------------------------------------
    # Newline-preference
    # ------------------------------------------------------------------

    def test_prefers_newline_over_hard_split(self) -> None:
        # 1500 'a's + newline + 1500 'b's = 3001 chars total.
        # With limit=2000, the newline falls within the window so the
        # first chunk should end with 'a\n' and the second start with 'b'.
        text = ("a" * 1500) + "\n" + ("b" * 1500)
        chunks = _split_message(text, limit=2000)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].endswith("\n"), repr(chunks[0][-5:]))
        self.assertTrue(chunks[1].startswith("b"), repr(chunks[1][:5]))
        self.assertEqual("".join(chunks), text)

    def test_multiple_sections_split_on_newlines(self) -> None:
        # Simulate a Markdown response with section headers.
        section = "## Header\n" + ("Line of text. " * 60) + "\n"
        text = section * 5  # 5 sections, likely > 2000 chars
        chunks = _split_message(text, limit=2000)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 2000)
        self.assertEqual("".join(chunks), text)

    def test_newline_at_exact_limit_boundary(self) -> None:
        # Newline is the 2000th character; it should end up in the first chunk.
        text = ("z" * 1999) + "\n" + ("y" * 500)
        chunks = _split_message(text, limit=2000)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), 2000)  # includes the '\n'
        self.assertEqual(chunks[1], "y" * 500)

    # ------------------------------------------------------------------
    # Small custom limit (easier to reason about)
    # ------------------------------------------------------------------

    def test_custom_limit_respected(self) -> None:
        text = "abcde fghij klmno"
        chunks = _split_message(text, limit=10)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 10)
        self.assertEqual("".join(chunks), text)


class SchedulerTests(unittest.TestCase):
    """Tests for scheduled-briefing constants and startup checks."""

    def test_scheduler_user_id_is_string(self) -> None:
        """_SCHEDULER_USER_ID must be a str so it's compatible with ADK session keys."""
        self.assertIsInstance(_SCHEDULER_USER_ID, str)

    def test_scheduler_user_id_is_not_empty(self) -> None:
        self.assertTrue(_SCHEDULER_USER_ID)

    def test_check_supabase_config_warns_when_url_missing(self) -> None:
        env_without_supabase = {
            k: v for k, v in os.environ.items()
            if k not in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        }
        with patch.dict(os.environ, env_without_supabase, clear=True):
            with self.assertLogs("daily_briefing.discord_bot", level=logging.WARNING) as cm:
                _check_supabase_config()
        self.assertTrue(any("Memory disabled" in line for line in cm.output))

    def test_check_supabase_config_silent_when_configured(self) -> None:
        env_with_supabase = dict(os.environ)
        env_with_supabase["SUPABASE_URL"] = "https://example.supabase.co"
        env_with_supabase["SUPABASE_SERVICE_ROLE_KEY"] = "fake-key"
        with patch.dict(os.environ, env_with_supabase, clear=True):
            # Should not raise and should not emit any warnings.
            try:
                with self.assertLogs("daily_briefing.discord_bot", level=logging.WARNING):
                    _check_supabase_config()
                self.fail("Expected no log output but got some")
            except AssertionError as exc:
                # assertLogs raises AssertionError when no logs are emitted — that's
                # the success case here.
                if "no logs" in str(exc).lower() or "0 log" in str(exc).lower():
                    pass  # expected: no warnings logged
                # If the AssertionError message is from self.fail(), re-raise.
                elif "Expected no log" in str(exc):
                    raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
