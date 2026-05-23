"""GNews API client."""

from __future__ import annotations

import requests


def fetch_top_headlines(
    api_key: str,
    lang: str = "en",
    max_results: int = 10,
) -> list[dict]:
    """Fetch top headlines from GNews.

    Args:
        api_key: GNews.io API key.
        lang: Language code (e.g. "en").
        max_results: Maximum number of articles to return.

    Returns:
        List of article dicts from the GNews response.

    Raises:
        requests.RequestException: On network or HTTP errors.
    """
    resp = requests.get(
        "https://gnews.io/api/v4/top-headlines",
        params={"token": api_key, "lang": lang, "max": max_results},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("articles", [])
