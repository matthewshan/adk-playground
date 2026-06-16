"""News tools — general GNews headlines and AI-focused RSS headlines."""

from __future__ import annotations

import datetime
import os

import requests

from daily_briefing.apis.gnews import fetch_top_headlines
from daily_briefing.apis.rss import fetch_feed

# Curated AI / ML RSS feeds — no API key required.
_AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://news.google.com/rss/search?q=(artificial+intelligence+OR+LLM+OR+OpenAI+OR+Anthropic)+when:1d&hl=en-US&gl=US&ceid=US:en",
]

_MIN_DT = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def get_news() -> str:
    """Fetch top general headlines from GNews.

    Required environment variables:
      GNEWS_API_KEY  — GNews.io API key (https://gnews.io)

    Returns:
        A bulleted string listing headline and source.
    """
    gnews_key = os.environ.get("GNEWS_API_KEY", "")
    if not gnews_key:
        return "News unavailable: GNEWS_API_KEY not set."

    try:
        articles = fetch_top_headlines(gnews_key)
    except requests.RequestException as exc:
        return f"News unavailable: {type(exc).__name__}: {exc}"

    seen: set[str] = set()
    lines: list[str] = []

    for article in articles:
        title = article.get("title", "").strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        source = (article.get("source") or {}).get("name", "GNews")
        lines.append(f"• {title} — {source}")

    return "\n".join(lines) if lines else "No news available."


def get_ai_news(max_results: int = 6) -> str:
    """Fetch recent AI / machine-learning headlines from curated RSS feeds.

    No API key required. Pulls from several AI-focused feeds, dedupes by title,
    and returns the most recent headlines first.

    Args:
        max_results: Maximum number of headlines to return.

    Returns:
        A bulleted string of "headline — source", or an error string.
    """
    items: list[dict] = []
    failures = 0
    for url in _AI_FEEDS:
        try:
            items.extend(fetch_feed(url, limit=10))
        except requests.RequestException:
            failures += 1

    if not items:
        return "AI news unavailable: all feeds failed." if failures else "No AI news available."

    items.sort(key=lambda i: i["published"] or _MIN_DT, reverse=True)

    seen: set[str] = set()
    lines: list[str] = []
    for item in items:
        title = item["title"].strip()
        if title.lower() in seen:
            continue
        seen.add(title.lower())
        lines.append(f"• {title} — {item['source']}")
        if len(lines) >= max_results:
            break

    return "\n".join(lines)
