"""Web-search tool — backend-agnostic ad-hoc search via Tavily.

Registered only on non-Gemini backends (Gemini uses native google_search).
"""

from __future__ import annotations

import os

import requests

from daily_briefing.apis.tavily import search


def web_search(query: str) -> str:
    """Search the web for recent or ad-hoc info outside weather/news/sports/calendar.

    Use for general questions, recent events the news tool doesn't cover, or when
    the user names something the dedicated tools can't resolve — including likely
    misspellings (e.g. a mistyped sports team).

    Args:
        query: What to search for.

    Returns:
        A synthesized answer (when available) followed by source bullets, or a
        "Web search unavailable: ..." string on failure.
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return "Web search unavailable: TAVILY_API_KEY not set."

    try:
        data = search(api_key, query)
    except requests.RequestException as exc:
        return f"Web search unavailable: {type(exc).__name__}: {exc}"

    answer = data.get("answer")
    results = data.get("results", [])
    if not answer and not results:
        return "No web results found."

    lines = [answer] if answer else []
    lines += [
        f"• {r.get('title', '')}: {r.get('content', '')} ({r.get('url', '')})"
        for r in results
    ]
    return "\n".join(lines)
