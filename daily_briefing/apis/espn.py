"""ESPN public API client — no key required."""

from __future__ import annotations

import datetime
import re

import requests


def find_team_id(sport: str, league: str, team_name: str) -> str | None:
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


def get_team_record(sport: str, league: str, team_id: str) -> str:
    """Fetch the current overall win-loss record for a team.

    Returns:
        Record string (e.g. "45-30"), or empty string if unavailable.

    Raises:
        requests.RequestException: If the ESPN team endpoint cannot be reached.
    """
    resp = requests.get(
        f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}",
        timeout=10,
    )
    resp.raise_for_status()
    record_items: list[dict] = (
        resp.json().get("team", {}).get("record", {}).get("items", [])
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


def get_team_schedule(sport: str, league: str, team_id: str) -> list[dict]:
    """Fetch the full list of schedule events for a team.

    Returns:
        List of raw event dicts from the ESPN team schedule endpoint.

    Raises:
        requests.RequestException: If the ESPN schedule endpoint cannot be reached.
    """
    resp = requests.get(
        f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/schedule",
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("events", [])


def is_preseason_event(event: dict) -> bool:
    """Return True when ESPN event metadata indicates a preseason game."""
    season = event.get("season") or {}
    if season.get("type") == 1:
        return True
    status_type = (event.get("status") or {}).get("type", {})
    tokens = [
        str(season.get("slug", "")),
        str(status_type.get("name", "")),
        str(status_type.get("description", "")),
        str(status_type.get("detail", "")),
        str(status_type.get("shortDetail", "")),
        str((event.get("week") or {}).get("text", "")),
    ]
    return any("preseason" in token.lower() for token in tokens)


def format_upcoming_event_line(event: dict, event_dt: datetime.datetime) -> str:
    """Format one upcoming/live ESPN event into a display string."""
    status_type = (event.get("status") or {}).get("type", {})
    short_detail: str = status_type.get("shortDetail", "")
    comps = event.get("competitions", [])
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

    event_date = event_dt.date()
    date_str = f"{event_date.strftime('%b')} {event_date.day}"
    preseason_suffix = " (Preseason)" if is_preseason_event(event) else ""
    return f"{date_str} @ {time_part} — {score_str}{preseason_suffix}"


def get_recent_results(
    sport: str,
    league: str,
    team_name: str,
    today: datetime.date,
    yesterday: datetime.date,
) -> list[tuple[datetime.date, str]]:
    """Fetch completed game results for yesterday and today from the scoreboard.

    Failures are silently swallowed — recent data is best-effort.

    Returns:
        List of (date, formatted_result_string) tuples for completed games.
    """
    recent_results: list[tuple[datetime.date, str]] = []
    for check_date in (yesterday, today):
        try:
            resp = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard",
                params={"dates": check_date.strftime("%Y%m%d")},
                timeout=10,
            )
            resp.raise_for_status()
            for event in resp.json().get("events", []):
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
                preseason_suffix = " (Preseason)" if is_preseason_event(event) else ""
                recent_results.append(
                    (check_date, f"{day_label}: {' vs '.join(score_parts)} — {sd}{preseason_suffix}")
                )
        except requests.RequestException:
            pass
    return recent_results


def get_upcoming_games(
    sched_events: list[dict], today: datetime.date
) -> list[tuple[datetime.date, str]]:
    """Parse upcoming (not-yet-completed) games from a team schedule event list.

    Args:
        sched_events: Raw event dicts from the ESPN team schedule endpoint.
        today: Events before this date are excluded.

    Returns:
        List of (date, formatted_game_string) tuples, sorted chronologically.
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
            continue
        upcoming.append((event_date, format_upcoming_event_line(event, event_dt)))

    upcoming.sort(key=lambda x: x[0])
    return upcoming


def get_today_scoreboard_upcoming_games(
    sport: str, league: str, team_name: str, today: datetime.date
) -> list[tuple[datetime.date, str]]:
    """Fallback: get today's live/scheduled games directly from the scoreboard."""
    upcoming: list[tuple[datetime.date, str]] = []
    try:
        resp = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard",
            params={"dates": today.strftime("%Y%m%d")},
            timeout=10,
        )
        resp.raise_for_status()
        for event in resp.json().get("events", []):
            if team_name.lower() not in event.get("name", "").lower():
                continue
            status_type = (event.get("status") or {}).get("type", {})
            if status_type.get("completed", False):
                continue
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
            upcoming.append((event_date, format_upcoming_event_line(event, event_dt)))
    except requests.RequestException:
        pass
    upcoming.sort(key=lambda x: x[0])
    return upcoming


def get_division_standings(sport: str, league: str, team_id: str) -> str:
    """Fetch the division standings table for the team's division.

    Returns:
        Formatted multi-line standings string, or empty string if unavailable.

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
