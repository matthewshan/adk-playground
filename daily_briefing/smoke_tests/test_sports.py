"""Sports tool tests.

Unit tests (always run):
  SportsFormattingTests — validates formatting logic with mocked API calls.

Smoke test (run when executed directly):
  Calls the real ESPN + TheSportsDB APIs and prints the formatted output.
"""

from __future__ import annotations

import datetime
import sys
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow running this file directly from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from daily_briefing.tools.sports import TrackedTeam, _get_upcoming_games, get_sports_scores

_SMOKE_TEAMS = [
    TrackedTeam("CFL", "football", "cfl", "Hamilton Tiger-Cats"),
    TrackedTeam("MLB", "baseball", "mlb", "Toronto Blue Jays"),
    TrackedTeam("NFL", "football", "nfl", "Detroit Lions"),
]

PASS = "✓ PASS"
FAIL = "✗ FAIL"


class SportsFormattingTests(unittest.TestCase):
    def test_upcoming_game_marks_preseason(self) -> None:
        today = datetime.date(2026, 5, 23)
        events = [
            {
                "date": "2026-05-23T20:00Z",
                "season": {"type": 1, "slug": "preseason"},
                "status": {"type": {"completed": False, "shortDetail": "5/23 - 4:00 PM ET"}},
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"displayName": "Hamilton Tiger-Cats"}, "score": ""},
                            {"team": {"displayName": "Toronto Argonauts"}, "score": ""},
                        ]
                    }
                ],
            }
        ]
        upcoming = _get_upcoming_games(events, today)
        self.assertEqual(len(upcoming), 1)
        self.assertIn("Preseason", upcoming[0][1])
        self.assertIn("4:00 PM ET", upcoming[0][1])

    @patch("daily_briefing.tools.sports._get_division_standings", return_value="")
    @patch("daily_briefing.tools.sports._get_today_scoreboard_upcoming_games")
    @patch("daily_briefing.tools.sports._get_upcoming_games", return_value=[])
    @patch("daily_briefing.tools.sports._get_recent_results", return_value=[])
    @patch("daily_briefing.tools.sports._get_team_record", return_value="0-0")
    @patch("daily_briefing.tools.sports._get_team_schedule", return_value=[])
    @patch("daily_briefing.tools.sports._find_team_id", return_value="17")
    def test_fallback_today_game_is_shown_and_not_offseason(
        self,
        _mock_team_id,
        _mock_schedule,
        _mock_record,
        _mock_recent,
        _mock_upcoming,
        mock_today_fallback,
        _mock_standings,
    ) -> None:
        mock_today_fallback.return_value = [
            (datetime.date(2026, 5, 23), "May 23 @ 4:00 PM ET — Hamilton Tiger-Cats vs Toronto Argonauts (Preseason)")
        ]
        teams = [TrackedTeam("CFL", "football", "cfl", "Hamilton Tiger-Cats")]
        with patch("daily_briefing.tools.sports.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(
                2026, 5, 23, 12, 0, tzinfo=datetime.timezone.utc
            )
            mock_dt.timezone.utc = datetime.timezone.utc
            mock_dt.timedelta = datetime.timedelta
            mock_dt.date = datetime.date
            output = get_sports_scores(teams)

        self.assertIn("CFL — Hamilton Tiger-Cats", output)
        self.assertIn("Upcoming:", output)
        self.assertIn("Preseason", output)
        self.assertIn("4:00 PM ET", output)
        self.assertNotIn("Off-season", output)


def run_smoke_test() -> bool:
    """Call the real APIs and print formatted output."""
    print("\n" + "=" * 60)
    print("SMOKE TEST — Live API calls")
    print("=" * 60)
    try:
        result = get_sports_scores(_SMOKE_TEAMS)
        print(result)
        for team in _SMOKE_TEAMS:
            assert team.league_label in result, f"{team.league_label} section missing from output"
        print(f"\n{PASS}")
        return True
    except Exception:
        print(f"\n{FAIL}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run unit tests first.
    suite = unittest.TestLoader().loadTestsFromTestCase(SportsFormattingTests)
    unit_result = unittest.TextTestRunner(verbosity=2).run(suite)

    # Then run live smoke test.
    smoke_ok = run_smoke_test()

    sys.exit(0 if unit_result.wasSuccessful() and smoke_ok else 1)