"""News tool — GNews top headlines."""

from __future__ import annotations

import os

import requests


def get_news() -> str:
    """Fetch top general headlines from GNews.

    Required environment variables:
      GNEWS_API_KEY  — GNews.io API key (https://gnews.io)

    Returns:
        A bulleted string listing headline and source.
    """
    gnews_key = os.environ["GNEWS_API_KEY"]

    seen: set[str] = set()
    lines: list[str] = []

    def _add_line(title: str, source: str) -> None:
        title = title.strip()
        if not title:
            return
        key = title.lower()
        if key in seen:
            return
        seen.add(key)
        lines.append(f"• {title} — {source}")

    # General top headlines — GNews
    gnews_resp = requests.get(
        "https://gnews.io/api/v4/top-headlines",
        params={"token": gnews_key, "lang": "en", "max": 10},
        timeout=10,
    )
    gnews_resp.raise_for_status()
    for article in gnews_resp.json().get("articles", []):
        _add_line(
            article.get("title", ""),
            (article.get("source") or {}).get("name", "GNews"),
        )

    return "\n".join(lines) if lines else "No news available."
