"""Google Calendar v3 API client via service account."""

from __future__ import annotations

from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def fetch_events(
    sa_info: dict,
    calendar_id: str,
    time_min: str,
    time_max: str,
) -> list[dict]:
    """Fetch calendar events from Google Calendar v3.

    Args:
        sa_info: Parsed service account JSON key dict.
        calendar_id: Calendar ID (e.g. "primary" or full email address).
        time_min: ISO 8601 start of the query window (inclusive).
        time_max: ISO 8601 end of the query window (exclusive).

    Returns:
        List of Google Calendar event dicts ordered by start time.

    Raises:
        googleapiclient.errors.HttpError: On API errors.
    """
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=_SCOPES
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result.get("items", [])
