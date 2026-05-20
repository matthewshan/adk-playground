#!/usr/bin/env python3
"""Smoke-test all daily briefing tools.

Free tools (no key required) are always run.
Keyed tools are skipped with a warning when the env var is absent.

Run from the repo root:
    python test_apis.py
"""

from __future__ import annotations

import os
import sys
import traceback

from pathlib import Path

# Resolve repo root regardless of where the script is invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# Load .env from the daily_briefing folder (next to .env.example).
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from daily_briefing.tools import TrackedTeam, get_news, get_sports_scores, get_weather
from daily_briefing.tools.calendar_events import get_calendar_events
from daily_briefing.tools.discord_webhook import send_discord

_DEFAULT_TEAMS = [
    TrackedTeam("MLB", "baseball", "mlb", "Toronto Blue Jays"),
    TrackedTeam("NFL", "football", "nfl", "Detroit Lions"),
    TrackedTeam("CFL", "football", "cfl", "Hamilton Tiger-Cats"),
]

PASS = "✓ PASS"
FAIL = "✗ FAIL"
SKIP = "– SKIP"


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
        result = get_sports_scores(_DEFAULT_TEAMS)
        print(result)
        assert result, "Result was empty"
        for league in ("NFL", "MLB", "CFL"):
            assert league in result, f"Expected {league} section in output"
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


def test_news() -> bool | None:
    _header("NEWS — GNews top headlines")
    key = os.getenv("GNEWS_API_KEY")
    if not key:
        print(f"{SKIP}  GNEWS_API_KEY not set — add it to .env to run this test")
        return None
    try:
        result = get_news()
        print(result)
        assert result, "Result was empty"
        assert "•" in result, "Expected bulleted headlines"
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


def test_calendar() -> bool | None:
    _header("CALENDAR — Google Calendar events")
    sa_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")
    if not sa_b64:
        print(f"{SKIP}  GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 not set — add it to .env to run this test")
        return None
    try:
        result = get_calendar_events()
        print(result)
        assert result, "Result was empty"
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


def test_discord() -> bool | None:
    _header("DISCORD — webhook delivery")
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        print(f"{SKIP}  DISCORD_WEBHOOK_URL not set — add it to .env to run this test")
        return None
    try:
        result = send_discord("🤖 daily-briefing smoke test")
        assert result == "Sent", f"Unexpected return value: {result!r}"
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


def main() -> int:
    tests = [test_weather_grand_rapids, test_sports_scores, test_news, test_calendar, test_discord]
    results = [t() for t in tests]
    passed = results.count(True)
    failed = results.count(False)
    skipped = results.count(None)
    print(f"\n{'─' * 60}")
    print(f"Results: {passed}/{len(results) - skipped} passed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
