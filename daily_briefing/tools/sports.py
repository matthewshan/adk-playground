"""Sports tool — orchestrates ESPN and TheSportsDB data for the daily briefing."""

from __future__ import annotations

import dataclasses
import datetime
import json
from zoneinfo import ZoneInfo

import requests

from daily_briefing.apis.espn import (
    find_team_id as _find_team_id,
    get_division_standings as _get_division_standings,
    get_game_plays as _get_game_plays,
    get_recent_results as _get_recent_results,
    get_team_record as _get_team_record,
    get_team_schedule as _get_team_schedule,
    get_today_scoreboard_upcoming_games as _get_today_scoreboard_upcoming_games,
    get_upcoming_games as _get_upcoming_games,
)
from daily_briefing.apis.thesportsdb import (
    get_recent_results as _tsdb_get_recent_results,
    get_team_events as _tsdb_get_team_events,
    get_team_record as _tsdb_get_team_record,
    get_upcoming_games as _tsdb_get_upcoming_games,
)


@dataclasses.dataclass
class TrackedTeam:
    """A sports team to include in the daily briefing.

    Attributes:
        league_label: Display label for the league (e.g. "MLB").
        sport: ESPN sport slug (e.g. "baseball", "football").
        league: ESPN league slug (e.g. "mlb", "nfl", "cfl").
        team_name: Full display name of the team (e.g. "Toronto Blue Jays").
    """

    league_label: str
    sport: str
    league: str
    team_name: str


_DEFAULT_TEAMS: list[TrackedTeam] = [
    TrackedTeam(league_label="NFL", sport="football", league="nfl", team_name="Detroit Lions"),
    TrackedTeam(league_label="MLB", sport="baseball", league="mlb", team_name="Toronto Blue Jays"),
    TrackedTeam(league_label="CFL", sport="football", league="cfl", team_name="Hamilton Tiger-Cats"),
]


def get_sports_scores(teams: list[dict] | None = None) -> str:
    """Return a JSON string with sports data for the given teams.

    Includes recent completed games, upcoming/live games, division standings,
    and team records. A game currently being played appears in ``upcoming_games``
    with ``"status": "in_progress"`` and live scores in ``competitors`` — use
    that to answer live/current-score questions.

    Tries ESPN first; falls back to TheSportsDB for leagues where ESPN has no
    current schedule data (e.g. CFL after 2023).

    Args:
        teams: Optional list of team objects. Omit to fetch the three default
            tracked teams (Detroit Lions, Toronto Blue Jays, Hamilton
            Tiger-Cats). To look up ANY other team (e.g. the user asks about
            the Chicago Cubs), pass a list of objects with keys:
              - league_label: display label, e.g. "MLB"
              - sport: ESPN sport slug — "baseball", "football", "basketball", "hockey"
              - league: ESPN league slug — "mlb", "nfl", "nba", "nhl", "cfl"
              - team_name: full team name, e.g. "Chicago Cubs"

    Returns:
        JSON string with keys:
          - as_of: current ET datetime string
          - teams: list of per-team objects, each with:
              league, team, record, note (null or off-season message),
              recent_games (list), upcoming_games (list, max 3), standings (dict or null)
    """
    # Fall back to defaults if called with no args OR if the LLM passed
    # something invalid (e.g. a list of strings instead of TrackedTeam objects).
    if not teams or not all(isinstance(t, (TrackedTeam, dict)) for t in teams):
        teams = _DEFAULT_TEAMS

    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    today = now_et.date()
    yesterday = today - datetime.timedelta(days=1)

    # Format as_of string
    hour = now_et.hour % 12 or 12
    ampm = "AM" if now_et.hour < 12 else "PM"
    as_of = f"{now_et.strftime('%A, %B')} {now_et.day}, {now_et.year} at {hour}:{now_et.strftime('%M')} {ampm} ET"

    team_results: list[dict] = []

    for team_entry in teams:
        if isinstance(team_entry, dict):
            team_entry = TrackedTeam(**team_entry)
        league_label = team_entry.league_label
        sport = team_entry.sport
        league = team_entry.league
        team_name = team_entry.team_name

        try:
            team_id = _find_team_id(sport, league, team_name)
            if not team_id:
                team_results.append({
                    "league": league_label,
                    "team": team_name,
                    "record": "",
                    "note": "team not found on ESPN",
                    "recent_games": [],
                    "upcoming_games": [],
                    "standings": None,
                })
                continue

            sched_events = _get_team_schedule(sport, league, team_id)
            record_str = _get_team_record(sport, league, team_id)

        except requests.RequestException as exc:
            team_results.append({
                "league": league_label,
                "team": team_name,
                "record": "",
                "note": f"error fetching data ({exc})",
                "recent_games": [],
                "upcoming_games": [],
                "standings": None,
            })
            continue

        recent_results = _get_recent_results(sport, league, team_name, today, yesterday)

        # Always query the scoreboard for today — the team schedule endpoint
        # doesn't update in real-time, so it can't detect a game in progress.
        # The scoreboard is the authoritative source for today's live status.
        today_games = _get_today_scoreboard_upcoming_games(sport, league, team_name, today)
        upcoming_from_schedule = _get_upcoming_games(sched_events, today)
        if today_games:
            # Scoreboard covers today; use schedule only for future dates.
            future_games = [g for g in upcoming_from_schedule if g["date"] > today.isoformat()]
            upcoming = today_games + future_games
        else:
            # No game on the scoreboard today; fall back to schedule only.
            upcoming = upcoming_from_schedule

        # TheSportsDB fallback when ESPN has no schedule or scoreboard data
        if not sched_events and not recent_results and not upcoming:
            tsdb_events = _tsdb_get_team_events(league_label, team_name, today.year)
            if tsdb_events:
                recent_results = _tsdb_get_recent_results(tsdb_events, today, yesterday)
                upcoming = _tsdb_get_upcoming_games(tsdb_events, today)
                record_str = _tsdb_get_team_record(tsdb_events, team_name)

        # Off-season: no recent games and next game is more than 30 days out
        next_date_str = upcoming[0]["date"] if upcoming else None
        next_date = datetime.date.fromisoformat(next_date_str) if next_date_str else None
        if not recent_results and (next_date is None or (next_date - today).days > 30):
            note = (
                f"Off-season (next game {next_date.strftime('%b')} {next_date.day}, {next_date.year})"
                if next_date
                else "Off-season (no games scheduled)"
            )
            team_results.append({
                "league": league_label,
                "team": team_name,
                "record": record_str,
                "note": note,
                "recent_games": [],
                "upcoming_games": [],
                "standings": None,
            })
            continue

        standings_data: dict | None = None
        try:
            standings_data = _get_division_standings(sport, league, team_id)
        except requests.RequestException:
            pass  # standings are best-effort

        team_results.append({
            "league": league_label,
            "team": team_name,
            "record": record_str,
            "note": None,
            "recent_games": sorted(recent_results, key=lambda g: g["date"]),
            "upcoming_games": upcoming[:3],
            "standings": standings_data,
        })

    return json.dumps({"as_of": as_of, "teams": team_results})


def get_game_plays(team_name: str | None = None) -> str:
    """Get live play-by-play data for a tracked team's in-progress game.

    Call this when the user asks about recent plays, what happened in a specific
    inning, how a run scored, who is currently batting or pitching, or the
    current count/baserunner situation.

    Args:
        team_name: Optional team name to look up (e.g. "Blue Jays", "Lions",
                   "Toronto"). Defaults to checking all tracked teams in order
                   and returning the first game found in progress.

    Returns:
        JSON string with keys:
          - game: full game name
          - status: "in_progress" or "scheduled"
          - detail: current inning/period string (e.g. "Top 3rd")
          - situation: balls, strikes, outs, on_first/second/third, current_at_bat text
          - recent_plays: last 15 narrative plays (inning, text, score, scoring_play)
          - scoring_plays: all plays where a run scored
        Returns a JSON error object if no in-progress game is found.
    """
    today = datetime.datetime.now(ZoneInfo("America/New_York")).date()

    teams_to_check = _DEFAULT_TEAMS
    if team_name:
        search = team_name.lower()
        matches = [
            t for t in _DEFAULT_TEAMS
            if search in t.team_name.lower() or t.team_name.lower() in search
        ]
        if matches:
            teams_to_check = matches

    for team in teams_to_check:
        result = _get_game_plays(team.sport, team.league, team.team_name, today)
        if result and result.get("status") == "in_progress":
            return json.dumps(result)

    checked = ", ".join(t.team_name for t in teams_to_check)
    return json.dumps({"error": f"No game currently in progress for: {checked}"})
