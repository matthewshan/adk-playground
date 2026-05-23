"""Sports tool — orchestrates ESPN and TheSportsDB data for the daily briefing."""

from __future__ import annotations

import dataclasses
import datetime

import requests

from daily_briefing.apis.espn import (
    find_team_id as _find_team_id,
    get_division_standings as _get_division_standings,
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


def get_sports_scores(teams: list[TrackedTeam]) -> str:
    """Fetch team record, recent results, next 3 upcoming games, and division
    standings for each tracked team.

    Tries ESPN first; falls back to TheSportsDB for leagues where ESPN has no
    current schedule data (e.g. CFL after 2023).

    Args:
        teams: List of TrackedTeam objects describing which teams to report on.

    Returns:
        Formatted per-team summary.
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()
    yesterday = today - datetime.timedelta(days=1)
    sections: list[str] = []

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
                sections.append(f"**{league_label} — {team_name}**: team not found on ESPN")
                continue

            sched_events = _get_team_schedule(sport, league, team_id)
            record_str = _get_team_record(sport, league, team_id)

        except requests.RequestException as exc:
            sections.append(f"**{league_label} — {team_name}**: error ({exc})")
            continue

        recent_results = _get_recent_results(sport, league, team_name, today, yesterday)
        upcoming = _get_upcoming_games(sched_events, today)
        if not upcoming:
            upcoming = _get_today_scoreboard_upcoming_games(sport, league, team_name, today)

        # TheSportsDB fallback when ESPN has no schedule or scoreboard data
        if not sched_events and not recent_results and not upcoming:
            tsdb_events = _tsdb_get_team_events(league_label, team_name, today.year)
            if tsdb_events:
                recent_results = _tsdb_get_recent_results(tsdb_events, today, yesterday)
                upcoming = _tsdb_get_upcoming_games(tsdb_events, today)
                record_str = _tsdb_get_team_record(tsdb_events, team_name)

        # Off-season: no recent games and next game is more than 30 days out
        next_date = upcoming[0][0] if upcoming else None
        if not recent_results and (next_date is None or (next_date - today).days > 30):
            next_str = (
                f"next game {next_date.strftime('%b')} {next_date.day}, {next_date.year}"
                if next_date
                else "no games scheduled"
            )
            sections.append(f"**{league_label} — {team_name}**: Off-season ({next_str})")
            continue

        record_suffix = f" ({record_str})" if record_str else ""
        lines = [f"**{league_label} — {team_name}{record_suffix}**"]

        recent_results.sort(key=lambda x: x[0])
        if recent_results:
            lines.append("  Recent:")
            lines.extend(f"    • {r}" for _, r in recent_results)
        else:
            lines.append("  Recent: No games in the last 2 days")

        if upcoming:
            lines.append("  Upcoming:")
            lines.extend(f"    • {g}" for _, g in upcoming[:3])
        else:
            lines.append("  Upcoming: None scheduled")

        try:
            standings_str = _get_division_standings(sport, league, team_id)
            if standings_str:
                lines.append(standings_str)
        except requests.RequestException:
            pass  # standings are best-effort

        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "No sports data available."