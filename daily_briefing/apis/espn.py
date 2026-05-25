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


def _parse_score(raw: object) -> str:
    """Return a plain score string from whatever ESPN puts in the score field."""
    if isinstance(raw, dict):
        return raw.get("displayValue", str(raw.get("value", "")))
    return str(raw) if raw is not None else ""


def _extract_competitors(event: dict) -> list[dict]:
    """Extract competitor team names and scores from an ESPN event."""
    comps = event.get("competitions", [])
    if not comps:
        return []
    return [
        {
            "team": (c.get("team") or {}).get("displayName", ""),
            "score": _parse_score(c.get("score")),
        }
        for c in comps[0].get("competitors", [])
    ]


def _game_time_utc(event: dict) -> str:
    """Return the ISO 8601 UTC game time string, or empty string if unavailable."""
    return event.get("date", "")


def _scheduled_time_et(event_dt: datetime.datetime) -> str:
    """Convert a UTC datetime to a 12-hour ET time string (EDT = UTC-4)."""
    local_hour = (event_dt.hour - 4) % 24
    am_pm = "PM" if local_hour >= 12 else "AM"
    h12 = local_hour % 12 or 12
    return f"{h12}:{event_dt.strftime('%M')} {am_pm} ET"


def get_recent_results(
    sport: str,
    league: str,
    team_name: str,
    today: datetime.date,
    yesterday: datetime.date,
) -> list[dict]:
    """Fetch completed game results for yesterday and today from the scoreboard.

    Failures are silently swallowed — recent data is best-effort.

    Returns:
        List of game dicts for completed games, each with keys:
        date, day_label, status ("final"), detail, is_preseason, competitors.
    """
    recent_results: list[dict] = []
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
                competitors = _extract_competitors(event)
                if not competitors:
                    continue
                day_label = "Today" if check_date == today else "Yesterday"
                recent_results.append({
                    "date": check_date.isoformat(),
                    "day_label": day_label,
                    "status": "final",
                    "detail": status_type.get("shortDetail", "Final"),
                    "is_preseason": is_preseason_event(event),
                    "competitors": competitors,
                })
        except requests.RequestException:
            pass
    return recent_results


def get_upcoming_games(
    sched_events: list[dict], today: datetime.date
) -> list[dict]:
    """Parse upcoming and in-progress games from a team schedule event list.

    Args:
        sched_events: Raw event dicts from the ESPN team schedule endpoint.
        today: Events before this date are excluded.

    Returns:
        List of game dicts sorted chronologically, each with keys:
        date, game_time_utc, status ("scheduled" or "in_progress"),
        detail, is_preseason, competitors.
    """
    upcoming: list[dict] = []
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
        status_type = (event.get("status") or {}).get("type", {})
        if status_type.get("completed", False):
            continue
        competitors = _extract_competitors(event)
        if not competitors:
            continue

        state = status_type.get("state", "pre")
        game_status = "in_progress" if state == "in" else "scheduled"

        # For scheduled games use the local time string; for live games use
        # shortDetail which contains clock/inning info (e.g. "Bottom 7th").
        short_detail = status_type.get("shortDetail", "")
        if game_status == "scheduled":
            time_part = re.sub(r"^\d+/\d+\s*-\s*", "", short_detail).strip()
            if not time_part or time_part.lower() in ("scheduled", "tbd"):
                time_part = _scheduled_time_et(event_dt)
            detail = time_part
        else:
            detail = short_detail

        upcoming.append({
            "date": event_date.isoformat(),
            "game_time_utc": event_date_str,
            "status": game_status,
            "detail": detail,
            "is_preseason": is_preseason_event(event),
            "competitors": competitors,
        })

    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def get_today_scoreboard_upcoming_games(
    sport: str, league: str, team_name: str, today: datetime.date
) -> list[dict]:
    """Fallback: get today's live/scheduled games directly from the scoreboard.

    Returns:
        List of game dicts in the same shape as get_upcoming_games().
    """
    upcoming: list[dict] = []
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
            competitors = _extract_competitors(event)
            if not competitors:
                continue

            state = status_type.get("state", "pre")
            game_status = "in_progress" if state == "in" else "scheduled"

            short_detail = status_type.get("shortDetail", "")
            if game_status == "scheduled":
                time_part = re.sub(r"^\d+/\d+\s*-\s*", "", short_detail).strip()
                if not time_part or time_part.lower() in ("scheduled", "tbd"):
                    time_part = _scheduled_time_et(event_dt)
                detail = time_part
            else:
                detail = short_detail

            upcoming.append({
                "date": event_date.isoformat(),
                "game_time_utc": event_date_str,
                "status": game_status,
                "detail": detail,
                "is_preseason": is_preseason_event(event),
                "competitors": competitors,
            })
    except requests.RequestException:
        pass
    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def get_game_plays(
    sport: str, league: str, team_name: str, today: datetime.date
) -> dict | None:
    """Fetch live play-by-play summary for a team's game today.

    Hits the scoreboard to find the event ID, then fetches the ESPN summary
    endpoint which contains pitch-level play data, the current game situation,
    and scoring plays.

    Args:
        sport: ESPN sport slug (e.g. "baseball").
        league: ESPN league slug (e.g. "mlb").
        team_name: Full team display name to match in the scoreboard.
        today: Date to query.

    Returns:
        Dict with keys: game, status, detail, situation, recent_plays (last 15
        narrative plays), scoring_plays (all plays where a run scored).
        Returns None if no game is found today or on any request error.
    """
    # Step 1: find the event ID from today's scoreboard.
    try:
        sb_resp = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard",
            params={"dates": today.strftime("%Y%m%d")},
            timeout=10,
        )
        sb_resp.raise_for_status()
        event_id = None
        event_name = None
        event_status_type: dict = {}
        for event in sb_resp.json().get("events", []):
            if team_name.lower() not in event.get("name", "").lower():
                continue
            event_id = event["id"]
            event_name = event.get("name", "")
            event_status_type = (event.get("status") or {}).get("type", {})
            break
        if not event_id:
            return None
    except requests.RequestException:
        return None

    # Step 2: fetch the full game summary.
    try:
        summary_resp = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary",
            params={"event": event_id},
            timeout=10,
        )
        summary_resp.raise_for_status()
        data = summary_resp.json()
    except requests.RequestException:
        return None

    all_plays = data.get("plays", [])

    # Readable plays: summaryType "N" = at-bat outcomes, "S" = scoring plays,
    # "I" = inning boundary markers. Exclude pitch-level ("P"), at-bat-start
    # ("A"), and empty-text plays.
    def _play_dict(p: dict) -> dict:
        return {
            "inning": p.get("period", {}).get("displayValue", ""),
            "text": p.get("text", ""),
            "away_score": p.get("awayScore", 0),
            "home_score": p.get("homeScore", 0),
            "scoring_play": p.get("scoringPlay", False),
        }

    narrative_plays = [
        _play_dict(p) for p in all_plays
        if p.get("summaryType") in ("N", "S", "I") and p.get("text")
    ]
    # Scoring plays from ALL play types — a run can score on any play type.
    scoring_plays = [_play_dict(p) for p in all_plays if p.get("scoringPlay")]

    # Current at-bat text (most recent "start-batterpitcher" play).
    current_at_bat = ""
    for p in reversed(all_plays):
        if p.get("type", {}).get("type") == "start-batterpitcher":
            current_at_bat = p.get("text", "")
            break

    # Situation: balls/strikes/outs/baserunners.
    sit = data.get("situation", {})
    situation = {
        "balls": sit.get("balls", 0),
        "strikes": sit.get("strikes", 0),
        "outs": sit.get("outs", 0),
        "on_first": sit.get("onFirst") is not None,
        "on_second": sit.get("onSecond") is not None,
        "on_third": sit.get("onThird") is not None,
        "current_at_bat": current_at_bat,
    }

    return {
        "game": event_name,
        "status": "in_progress" if event_status_type.get("state") == "in" else "scheduled",
        "detail": event_status_type.get("shortDetail", ""),
        "situation": situation,
        "recent_plays": narrative_plays[-15:],
        "scoring_plays": scoring_plays,
    }


def get_division_standings(sport: str, league: str, team_id: str) -> dict | None:
    """Fetch the division standings table for the team's division.

    Returns:
        Dict with keys "division" (str) and "teams" (list of team dicts with
        keys: team, record, games_behind, is_tracked). Returns None if the
        team's division cannot be found.

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
        teams: list[dict] = []
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
            is_tracked = str(entry.get("team", {}).get("id", "")) == team_id
            teams.append({
                "team": t_name,
                "record": record,
                "games_behind": gb if gb else "-",
                "is_tracked": is_tracked,
            })
        return {"division": group_name, "teams": teams}

    return None
