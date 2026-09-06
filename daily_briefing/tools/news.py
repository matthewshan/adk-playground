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


def _format_headline(title: str, link: str, source: str) -> str:
    """Render `• [Title](url) — Source`, unlinked when there is no http(s) link.

    Masked link rather than a bare URL: Discord renders it clickable in bot
    messages without adding a link-preview embed per headline.
    """
    label = title.replace("[", "(").replace("]", ")")  # a ] would end the label early
    url = link.strip()
    if not url.startswith(("http://", "https://")):
        return f"• {label} — {source}"
    url = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")  # would close the target
    return f"• [{label}]({url}) — {source}"


def get_news() -> str:
    """Fetch top general headlines from GNews.

    Required environment variables:
      GNEWS_API_KEY  — GNews.io API key (https://gnews.io)

    Returns:
        A bulleted string of "• [headline](link) — source" lines.
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
        lines.append(_format_headline(title, article.get("url", ""), source))

    return "\n".join(lines) if lines else "No news available."


def get_ai_news(max_results: int = 6) -> str:
    """Fetch recent AI / machine-learning headlines from curated RSS feeds.

    No API key required. Pulls from several AI-focused feeds, dedupes by title,
    and returns the most recent headlines first.

    Args:
        max_results: Maximum number of headlines to return.

    Returns:
        A bulleted string of "• [headline](link) — source" lines, or an error
        string.
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
        lines.append(_format_headline(title, item["link"], item["source"]))
        if len(lines) >= max_results:
            break

    return "\n".join(lines)
