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
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + datetime.timedelta(days=1)

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
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
            hour = dt.hour % 12 or 12
            time_str = f"{hour}:{dt.strftime('%M %p')}"
        else:
            time_str = "all day"
        lines.append(f"• {summary} @ {time_str}")

    return "\n".join(lines)
