"""TheSportsDB API client — free public key, no registration required."""

from __future__ import annotations

import datetime

import requests

_FREE_KEY = "3"


def get_team_events(league_label: str, team_name: str, year: int) -> list[dict]:
    """Return all season events for *team_name* from TheSportsDB.

    Discovers the league ID by searching *league_label* (e.g. "CFL"), fetches
    all events for *year*, and filters to those involving *team_name*.

    Returns:
        List of event dicts for the team, or empty list on any error.
    """
    try:
        teams_resp = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/{_FREE_KEY}/search_all_teams.php",
            params={"l": league_label},
            timeout=10,
        )
        teams_resp.raise_for_status()
        all_teams = teams_resp.json().get("teams") or []
        team_lower = team_name.lower()
        league_id: str | None = None
        for t in all_teams:
            t_name = t.get("strTeam", "").lower()
            if team_lower == t_name or team_lower in t_name or t_name in team_lower:
                league_id = str(t.get("idLeague", ""))
                break
        if not league_id:
            return []

        sched_resp = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/{_FREE_KEY}/eventsseason.php",
            params={"id": league_id, "s": str(year)},
            timeout=10,
        )
        sched_resp.raise_for_status()
        all_events = sched_resp.json().get("events") or []
        return [
            e for e in all_events
            if team_lower in e.get("strHomeTeam", "").lower()
            or team_lower in e.get("strAwayTeam", "").lower()
        ]
    except requests.RequestException:
        return []


def is_preseason(event: dict) -> bool:
    """Return True when the round number indicates preseason (>= 100)."""
    try:
        return int(event.get("intRound") or 0) >= 100
    except (ValueError, TypeError):
        return False


def format_event_line(event: dict) -> str:
    """Format a TheSportsDB event into a display string (time shown in ET)."""
    home = event.get("strHomeTeam", "?")
    away = event.get("strAwayTeam", "?")
    timestamp = event.get("strTimestamp", "")
    date_str = "?"
    time_str = ""
    if timestamp:
        try:
            event_dt = datetime.datetime.fromisoformat(timestamp).replace(
                tzinfo=datetime.timezone.utc
            )
            event_date = event_dt.date()
            date_str = f"{event_date.strftime('%b')} {event_date.day}"
            edt_hour = (event_dt.hour - 4) % 24
            h12 = edt_hour % 12 or 12
            am_pm = "PM" if edt_hour >= 12 else "AM"
            time_str = f"{h12}:{event_dt.strftime('%M')} {am_pm} ET"
        except (ValueError, AttributeError):
            pass
    preseason_suffix = " (Preseason)" if is_preseason(event) else ""
    return f"{date_str} @ {time_str} — {home} vs {away}{preseason_suffix}"


def get_team_record(events: list[dict], team_name: str) -> str:
    """Compute a W-L record by tallying completed events.

    Args:
        events: Season event dicts already filtered to the team (from get_team_events).
        team_name: Full display name used to identify home/away side.

    Returns:
        Record string like "3-1", or empty string if no completed games.
    """
    wins = losses = 0
    team_lower = team_name.lower()
    for e in events:
        if e.get("strStatus") not in ("FT", "AET", "PEN"):
            continue
        try:
            hs = int(e.get("intHomeScore") or 0)
            aws = int(e.get("intAwayScore") or 0)
        except (ValueError, TypeError):
            continue
        is_home = team_lower in e.get("strHomeTeam", "").lower()
        team_scored = hs if is_home else aws
        opp_scored = aws if is_home else hs
        if team_scored > opp_scored:
            wins += 1
        else:
            losses += 1
    return f"{wins}-{losses}" if (wins or losses) else ""


def get_recent_results(
    events: list[dict], today: datetime.date, yesterday: datetime.date
) -> list[tuple[datetime.date, str]]:
    """Extract completed games from TheSportsDB events for today/yesterday."""
    results: list[tuple[datetime.date, str]] = []
    for e in events:
        if e.get("strStatus") not in ("FT", "AET", "PEN"):
            continue
        try:
            event_date = datetime.date.fromisoformat(e.get("dateEvent", ""))
        except (ValueError, AttributeError):
            continue
        if event_date not in (today, yesterday):
            continue
        home = e.get("strHomeTeam", "?")
        away = e.get("strAwayTeam", "?")
        hs = e.get("intHomeScore") or ""
        aws = e.get("intAwayScore") or ""
        day_label = "Today" if event_date == today else "Yesterday"
        preseason_suffix = " (Preseason)" if is_preseason(e) else ""
        results.append(
            (event_date, f"{day_label}: {home} {hs} vs {away} {aws} — Final{preseason_suffix}")
        )
    return results


def get_upcoming_games(
    events: list[dict], today: datetime.date
) -> list[tuple[datetime.date, str]]:
    """Extract not-yet-started games on or after *today*."""
    upcoming: list[tuple[datetime.date, str]] = []
    for e in events:
        if e.get("strPostponed", "no") == "yes":
            continue
        if e.get("strStatus") in ("FT", "AET", "PEN"):
            continue
        try:
            event_date = datetime.date.fromisoformat(e.get("dateEvent", ""))
        except (ValueError, AttributeError):
            continue
        if event_date < today:
            continue
        upcoming.append((event_date, format_event_line(e)))
    upcoming.sort(key=lambda x: x[0])
    return upcoming
