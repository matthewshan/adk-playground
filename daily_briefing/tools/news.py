"""News tool — formats GNews headlines for the daily briefing."""

from __future__ import annotations

import os

from daily_briefing.apis.gnews import fetch_top_headlines


def get_news() -> str:
    """Fetch top general headlines from GNews.

    Required environment variables:
      GNEWS_API_KEY  — GNews.io API key (https://gnews.io)

    Returns:
        A bulleted string listing headline and source.
    """
    gnews_key = os.environ["GNEWS_API_KEY"]
    articles = fetch_top_headlines(gnews_key)

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
