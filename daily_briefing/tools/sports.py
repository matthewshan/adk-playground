"""Sports tool — ESPN public API (no key required)."""

from __future__ import annotations

import dataclasses
import datetime
import re

import requests


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


def _find_team_id(sport: str, league: str, team_name: str) -> str | None:
    """Return the ESPN numeric team ID for *team_name*, or None if not found."""
    resp = requests.get(
        f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams",
        params={"limit": 100},
        timeout=10,
    )
    resp.raise_for_status()
    search = team_name.lower()
    all_teams = (
        t.get("team", {})
        for s in resp.json().get("sports", [])
        for lg in s.get("leagues", [])
        for t in lg.get("teams", [])
    )
    for team in all_teams:
        display = team.get("displayName", "").lower()
        if search == display or search in display or display in search:
            return str(team.get("id", ""))
    return None


def _get_team_record(sport: str, league: str, team_id: str) -> str:
    """Fetch the current overall win-loss record for a team.

    Args:
        sport: ESPN sport slug (e.g. "baseball").
        league: ESPN league slug (e.g. "mlb").
        team_id: ESPN numeric team ID.

    Returns:
        Record summary string (e.g. "45-30"), or empty string if unavailable.

    Raises:
        requests.RequestException: If the ESPN team endpoint cannot be reached.
    """
    info_resp = requests.get(
        f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}",
        timeout=10,
    )
    info_resp.raise_for_status()
    record_items: list[dict] = (
        info_resp.json().get("team", {}).get("record", {}).get("items", [])
    )
    record_by_name = {
        item.get("name", "").lower(): item.get("summary", "")
        for item in record_items
    }
    return (
        record_by_name.get("overall")
        or record_by_name.get("total")
        or (record_items[0].get("summary", "") if record_items else "")
    )


def _get_team_schedule(sport: str, league: str, team_id: str) -> list[dict]:
    """Fetch the full list of schedule events for a team.

    Args:
        sport: ESPN sport slug (e.g. "baseball").
        league: ESPN league slug (e.g. "mlb").
        team_id: ESPN numeric team ID.

    Returns:
        List of raw event dicts from the ESPN team schedule endpoint.

    Raises:
        requests.RequestException: If the ESPN schedule endpoint cannot be reached.
    """
    sched_resp = requests.get(
        f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/schedule",
        timeout=10,
    )
    sched_resp.raise_for_status()
    return sched_resp.json().get("events", [])


def _get_recent_results(
    sport: str,
    league: str,
    team_name: str,
    today: datetime.date,
    yesterday: datetime.date,
) -> list[tuple[datetime.date, str]]:
    """Fetch completed game results for yesterday and today from the scoreboard.

    Checks both yesterday and today to capture same-day results and late games.
    Failures are silently swallowed because recent data is best-effort.

    Args:
        sport: ESPN sport slug (e.g. "baseball").
        league: ESPN league slug (e.g. "mlb").
        team_name: Full display name used to match events (e.g. "Toronto Blue Jays").
        today: The current UTC date.
        yesterday: The previous UTC date.

    Returns:
        List of (date, formatted_result_string) tuples for completed games,
        in the order they were found (yesterday first, then today).
    """
    recent_results: list[tuple[datetime.date, str]] = []
    for check_date in (yesterday, today):
        try:
            sb_resp = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard",
                params={"dates": check_date.strftime("%Y%m%d")},
                timeout=10,
            )
            sb_resp.raise_for_status()
            for event in sb_resp.json().get("events", []):
                if team_name.lower() not in event.get("name", "").lower():
                    continue
                status_type = (event.get("status") or {}).get("type", {})
                if not status_type.get("completed", False):
                    continue
                comps = event.get("competitions", [])
                if not comps:
                    continue
                score_parts = [
                    f"{(c.get('team') or {}).get('displayName', '')} {c.get('score', '')}".strip()
                    for c in comps[0].get("competitors", [])
                ]
                day_label = "Today" if check_date == today else "Yesterday"
                sd = status_type.get("shortDetail", "Final")
                recent_results.append(
                    (check_date, f"{day_label}: {' vs '.join(score_parts)} — {sd}")
                )
        except requests.RequestException:
            pass  # recent data is best-effort
    return recent_results


def _get_upcoming_games(
    sched_events: list[dict], today: datetime.date
) -> list[tuple[datetime.date, str]]:
    """Parse upcoming (not-yet-completed) games from a team schedule event list.

    Args:
        sched_events: Raw event dicts from the ESPN team schedule endpoint.
        today: The current UTC date; events before this date are excluded.

    Returns:
        List of (date, formatted_game_string) tuples for future games,
        sorted chronologically.
    """
    upcoming: list[tuple[datetime.date, str]] = []
    for event in sched_events:
        event_date_str = event.get("date", "")
        if not event_date_str:
            continue
        try:
            event_dt = datetime.datetime.fromisoformat(
                event_date_str.replace("Z", "+00:00")
            )
        except ValueError:
            continue
        event_date = event_dt.date()
        if event_date < today:
            continue

        comps = event.get("competitions", [])
        if not comps:
            continue
        status_type = (event.get("status") or {}).get("type", {})
        if status_type.get("completed", False):
            continue  # already captured in recent_results

        short_detail: str = status_type.get("shortDetail", "")
        score_parts = [
            f"{(c.get('team') or {}).get('displayName', '')} {c.get('score', '')}".strip()
            for c in comps[0].get("competitors", [])
        ]
        score_str = " vs ".join(score_parts)

        # Strip leading "M/D - " from shortDetail; fall back to UTC-4 (EDT) derivation
        time_part = re.sub(r"^\d+/\d+\s*-\s*", "", short_detail).strip()
        if not time_part or time_part.lower() in ("scheduled", "tbd"):
            local_hour = (event_dt.hour - 4) % 24
            am_pm = "PM" if local_hour >= 12 else "AM"
            h12 = local_hour % 12 or 12
            time_part = f"{h12}:{event_dt.strftime('%M')} {am_pm} EDT"
        date_str = f"{event_date.strftime('%b')} {event_date.day}"
        upcoming.append((event_date, f"{date_str} @ {time_part} — {score_str}"))

    upcoming.sort(key=lambda x: x[0])
    return upcoming


def _get_division_standings(sport: str, league: str, team_id: str) -> str:
    """Fetch the division standings table for the team's division.

    Walks the ESPN standings response tree to locate the group (division) that
    contains *team_id* and formats a compact leaderboard, marking the tracked
    team with a pointer.

    Args:
        sport: ESPN sport slug (e.g. "baseball").
        league: ESPN league slug (e.g. "mlb").
        team_id: ESPN numeric team ID used to locate the correct division group.

    Returns:
        Formatted multi-line standings string, or empty string if standings are
        unavailable for this league.

    Raises:
        requests.RequestException: If the ESPN standings endpoint cannot be reached.
    """
    resp = requests.get(
        f"https://site.api.espn.com/apis/v2/sports/{sport}/{league}/standings",
        params={"level": 3},
        timeout=10,
    )
    resp.raise_for_status()

    def _iter_groups(node: dict):
        """Yield *node* and every descendant via depth-first traversal."""
        yield node
        for child in node.get("children", []):
            yield from _iter_groups(child)

    for group in _iter_groups(resp.json()):
        entries: list[dict] = group.get("standings", {}).get("entries", [])
        if not any(str(e.get("team", {}).get("id", "")) == team_id for e in entries):
            continue

        group_name = group.get("name", "Division")
        rows: list[str] = [f"  {group_name} Standings:"]
        for entry in entries:
            t_name = entry.get("team", {}).get("displayName", "?")
            stats = {
                s.get("name", "").lower(): s.get("displayValue", "")
                for s in entry.get("stats", [])
            }
            record = stats.get("overall") or (
                f"{stats.get('wins', '?')}-{stats.get('losses', '?')}"
            )
            gb = stats.get("gamesbehind") or stats.get("gamesback", "")
            gb_str = f", {gb} GB" if gb and gb not in ("-", "0", "0.0") else ""
            marker = " ◀" if str(entry.get("team", {}).get("id", "")) == team_id else ""
            rows.append(f"    {t_name}: {record}{gb_str}{marker}")
        return "\n".join(rows)

    return ""


def get_sports_scores(teams: list[TrackedTeam]) -> str:
    """Fetch team record, recent results, next 3 upcoming games, and division
    standings for each tracked team.

    Args:
        teams: List of TrackedTeam objects describing which teams to report on.

    Returns:
        Formatted per-team summary.
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()
    yesterday = today - datetime.timedelta(days=1)
    sections: list[str] = []

    for team_entry in teams:
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
