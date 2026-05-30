"""Tavily Search API client — LLM-oriented web search (no SDK, plain POST)."""

from __future__ import annotations

import requests

_URL = "https://api.tavily.com/search"


def search(api_key: str, query: str, max_results: int = 5) -> dict:
    """Search the web via Tavily.

    Args:
        api_key: Tavily API key (https://tavily.com).
        query: Search query.
        max_results: Maximum results to return.

    Returns:
        Parsed JSON dict — "answer" (str | None) plus "results", a list of
        {title, url, content, ...} dicts.

    Raises:
        requests.RequestException: On network or HTTP errors.
    """
    resp = requests.post(
        _URL,
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": True,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
