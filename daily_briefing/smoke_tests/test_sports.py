"""Sports tool tests.

Unit tests (always run):
  SportsFormattingTests — validates data structure with mocked API calls.

Smoke test (run when executed directly):
  Calls the real ESPN + TheSportsDB APIs and prints the formatted output.
"""

from __future__ import annotations

import datetime
import json
import sys
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

# Force UTF-8 output so emoji/Unicode in standings don't crash on Windows
# (default cp1252 terminal codec cannot encode ◀ and similar characters).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
                "status": {"type": {
                    "completed": False,
                    "state": "pre",
                    "shortDetail": "5/23 - 4:00 PM ET",
                }},
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
        game = upcoming[0]
        self.assertTrue(game["is_preseason"], "Expected is_preseason to be True")
        self.assertIn("4:00 PM ET", game["detail"])
        self.assertEqual(game["status"], "scheduled")

    def test_in_progress_game_has_correct_status(self) -> None:
        today = datetime.date(2026, 5, 23)
        events = [
            {
                "date": "2026-05-23T20:00Z",
                "season": {"type": 2, "slug": "regular-season"},
                "status": {"type": {
                    "completed": False,
                    "state": "in",
                    "shortDetail": "Bottom 7th",
                }},
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"displayName": "Toronto Blue Jays"}, "score": "3"},
                            {"team": {"displayName": "Boston Red Sox"}, "score": "5"},
                        ]
                    }
                ],
            }
        ]
        upcoming = _get_upcoming_games(events, today)
        self.assertEqual(len(upcoming), 1)
        game = upcoming[0]
        self.assertEqual(game["status"], "in_progress")
        self.assertEqual(game["detail"], "Bottom 7th")
        scores = {c["team"]: c["score"] for c in game["competitors"]}
        self.assertEqual(scores["Toronto Blue Jays"], "3")
        self.assertEqual(scores["Boston Red Sox"], "5")

    @patch("daily_briefing.tools.sports._get_division_standings", return_value=None)
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
            {
                "date": "2026-05-23",
                "game_time_utc": "2026-05-23T20:00:00+00:00",
                "status": "scheduled",
                "detail": "4:00 PM ET",
                "is_preseason": True,
                "competitors": [
                    {"team": "Hamilton Tiger-Cats", "score": ""},
                    {"team": "Toronto Argonauts", "score": ""},
                ],
            }
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

        data = json.loads(output)
        self.assertEqual(len(data["teams"]), 1)
        team = data["teams"][0]
        self.assertEqual(team["league"], "CFL")
        self.assertEqual(team["team"], "Hamilton Tiger-Cats")
        self.assertIsNone(team["note"], "Expected no off-season note")
        self.assertEqual(len(team["upcoming_games"]), 1)
        game = team["upcoming_games"][0]
        self.assertTrue(game["is_preseason"])
        self.assertIn("4:00 PM ET", game["detail"])


def run_smoke_test() -> bool:
    """Call the real APIs and print formatted output."""
    print("\n" + "=" * 60)
    print("SMOKE TEST — Live API calls")
    print("=" * 60)
    try:
        result = get_sports_scores(_SMOKE_TEAMS)
        print(result)
        data = json.loads(result)
        league_labels = {t["league"] for t in data["teams"]}
        for team in _SMOKE_TEAMS:
            assert team.league_label in league_labels, (
                f"{team.league_label} section missing from output"
            )
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
