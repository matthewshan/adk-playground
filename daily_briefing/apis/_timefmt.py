"""Shared time formatting for the API clients."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def et_time_str(utc_dt: datetime.datetime) -> str:
    """Format a UTC datetime as a 12-hour ET clock string, e.g. "7:30 PM ET".

    Uses a real tz database conversion so EST (UTC-5) and EDT (UTC-4) are both
    correct — the previous hardcoded ``hour - 4`` showed winter games an hour
    early. A naive datetime is assumed to already be UTC.
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)
    et = utc_dt.astimezone(_ET)
    h12 = et.hour % 12 or 12
    am_pm = "PM" if et.hour >= 12 else "AM"
    return f"{h12}:{et.strftime('%M')} {am_pm} ET"
