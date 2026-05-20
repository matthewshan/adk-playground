#!/usr/bin/env python3
"""Smoke-test the free (no API key) tools: Open-Meteo weather and ESPN sports.

Run from the repo root:
    python test_free_apis.py
"""

from __future__ import annotations

import sys
import traceback

# Ensure the repo root is on the path so daily_briefing is importable.
sys.path.insert(0, ".")

from daily_briefing.tools import get_sports_scores, get_weather

PASS = "✓ PASS"
FAIL = "✗ FAIL"


def _header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def test_weather_grand_rapids() -> bool:
    _header("WEATHER — Grand Rapids, MI (42.96, -85.67)")
    try:
        result = get_weather(42.96, -85.67)
        print(result)
        assert result, "Result was empty"
        assert "°F" in result, "Expected a Fahrenheit temperature"
        assert "wind" in result, "Expected wind speed"
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


def test_sports_scores() -> bool:
    _header("SPORTS — ESPN scoreboard (NFL / MLB / CFL)")
    try:
        result = get_sports_scores()
        print(result)
        assert result, "Result was empty"
        # Each league section should appear
        for league in ("NFL", "MLB", "CFL"):
            assert league in result, f"Expected {league} section in output"
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


def main() -> int:
    tests = [test_weather_grand_rapids, test_sports_scores]
    results = [t() for t in tests]
    failed = results.count(False)
    print(f"\n{'─' * 60}")
    print(f"Results: {results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
