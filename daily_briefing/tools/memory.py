"""Memory tools — store and retrieve session memories backed by Supabase pgvector.

Embeddings are generated automatically via Google's text-embedding-004 model
(768 dimensions, matching the agent_memory table schema).  The agent only needs
to pass plain text; this module handles the embedding round-trip transparently.

Usage (registered in agent.py):
    from daily_briefing.tools.memory import remember, recall
"""

from __future__ import annotations

import os

import google.generativeai as genai

from daily_briefing.apis.supabase import insert_memory, similarity_search

_EMBED_MODEL = "models/text-embedding-004"


def _embed(text: str) -> list[float]:
    """Return a 768-dimensional embedding for *text* using Google's embedding model."""
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    result = genai.embed_content(model=_EMBED_MODEL, content=text)
    return result["embedding"]


# ---------------------------------------------------------------------------
# ADK-registered tools
# ---------------------------------------------------------------------------


def remember(session_id: str, content: str) -> str:
    """Persist a piece of information to long-term memory for later retrieval.

    Call this whenever the user shares something worth remembering across
    sessions (a preference, a fact, a completed task, etc.).

    Args:
        session_id: Unique identifier for the current conversation session.
        content: The text to store as a memory (one coherent idea per call).

    Returns:
        Confirmation message on success.
    """
    embedding = _embed(content)
    insert_memory(session_id=session_id, content=content, embedding=embedding)
    return f"Stored memory for session {session_id!r}: {content[:80]}{'…' if len(content) > 80 else ''}"


def recall(query: str, session_id: str | None = None, limit: int = 5) -> str:
    """Search long-term memory for entries semantically similar to *query*.

    Args:
        query: Natural-language question or phrase to search for.
        session_id: If provided, restrict results to this session only.
            Leave blank to search across all sessions.
        limit: Maximum number of results to return (1–20).

    Returns:
        Numbered list of matching memories with similarity scores, or a
        message indicating no matches were found.
    """
    limit = max(1, min(limit, 20))
    embedding = _embed(query)
    rows = similarity_search(embedding=embedding, session_id=session_id, limit=limit)

    if not rows:
        scope = f"session {session_id!r}" if session_id else "all sessions"
        return f"No memories found for {scope} matching: {query!r}"

    lines = [f"Top {len(rows)} memory result(s) for {query!r}:\n"]
    for i, row in enumerate(rows, start=1):
        sim_pct = round(row["similarity"] * 100, 1)
        lines.append(f"{i}. [{sim_pct}% match | session={row['session_id']}]\n   {row['content']}")
    return "\n".join(lines)
