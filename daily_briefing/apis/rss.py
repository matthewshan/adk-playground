"""Minimal RSS reader — stdlib XML parsing, no extra dependencies."""

from __future__ import annotations

import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

_TIMEOUT = 10
_HEADERS = {"User-Agent": "daily-briefing/1.0 (+https://github.com/matthewshan/adk-playground)"}


def fetch_feed(url: str, limit: int = 10) -> list[dict]:
    """Fetch and parse an RSS feed into item dicts.

    Args:
        url: RSS feed URL.
        limit: Max items to return.

    Returns:
        List of dicts with keys: title, link, source, published (tz-aware
        datetime or None).

    Raises:
        requests.RequestException: On network or HTTP errors.
    """
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)

    channel_title = (root.findtext("./channel/title") or "").strip()
    items: list[dict] = []
    for item in root.iterfind("./channel/item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        items.append({
            "title": title,
            "link": (item.findtext("link") or "").strip(),
            "source": (item.findtext("source") or channel_title).strip(),
            "published": _parse_date(item.findtext("pubDate")),
        })
        if len(items) >= limit:
            break
    return items


def _parse_date(raw: str | None) -> datetime.datetime | None:
    """Parse an RFC-822 pubDate into a tz-aware datetime (assume UTC if naive)."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt
