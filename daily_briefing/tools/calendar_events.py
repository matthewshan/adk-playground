"""Calendar tool — Google Calendar v3 via service account."""

from __future__ import annotations

import base64
import datetime
import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_events() -> str:
    """Fetch today's events from a private Google Calendar via service account.

    Required environment variables:
      GOOGLE_CALENDAR_ID                   — Calendar ID (full address or "primary")
      GOOGLE_SERVICE_ACCOUNT_JSON_BASE64   — base64-encoded service account JSON key

    Returns:
        A bulleted list of event titles and times, or "Nothing scheduled".
    """
    sa_b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "")
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    if not sa_b64:
        return "Calendar unavailable: GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 not set."

    sa_info = json.loads(base64.b64decode(sa_b64).decode("utf-8"))
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=_CALENDAR_SCOPES
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_window = start_of_day + datetime.timedelta(days=7)

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_window.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    items: list[dict] = result.get("items", [])
    if not items:
        return "Nothing scheduled"

    lines: list[str] = []
    for event in items:
        summary = event.get("summary", "(no title)")
        start = event.get("start", {})
        if "dateTime" in start:
            dt = datetime.datetime.fromisoformat(start["dateTime"])
            event_date = dt.date()
            hour = dt.hour % 12 or 12
            time_str = f"{hour}:{dt.strftime('%M %p')}"
        else:
            event_date = datetime.date.fromisoformat(start["date"])
            time_str = "all day"

        delta = (event_date - today).days
        if delta == 0:
            direction = "Today"
        elif delta == 1:
            direction = "Tomorrow"
        else:
            direction = f"In {delta} days"

        day_str = event_date.strftime("%a %b ") + str(event_date.day)
        lines.append(f"• {summary} @ {time_str}  [{day_str} — {direction}]")

    return "\n".join(lines)
