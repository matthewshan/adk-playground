"""
Unit tests for daily_briefing/discord_bot.py — no Discord token required.

Tests the _split_message helper in isolation, covering:
  - Short messages that fit in a single chunk
  - Long messages that must be split into multiple chunks
  - Preference for newline boundaries over hard character splits
  - Edge cases (empty string, exact-limit length)

Run:
    python daily_briefing/smoke_tests/test_discord_bot.py
"""

import sys
import unittest
from pathlib import Path

# Allow running from the repo root or the smoke_tests/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from daily_briefing.discord_bot import _split_message


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
