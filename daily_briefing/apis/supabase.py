"""Supabase pgvector client — low-level store and similarity-search operations."""

from __future__ import annotations

import os

from supabase import Client, create_client

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError(
                "Supabase is not configured: SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY must both be set."
            )
        _client = create_client(url, key)
    return _client


def insert_memory(session_id: str, content: str, embedding: list[float]) -> None:
    """Persist a text chunk and its embedding for a given session."""
    _get_client().table("agent_memory").insert(
        {"session_id": session_id, "content": content, "embedding": embedding}
    ).execute()


def similarity_search(
    embedding: list[float],
    session_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return the top-k most similar memory entries via the match_agent_memory RPC.

    Args:
        embedding: Query embedding vector.
        session_id: If provided, filter results to this session only.
        limit: Maximum number of results to return.

    Returns:
        List of dicts with keys: id, session_id, content, similarity.
    """
    # When filtering by session_id in Python we over-fetch from the DB so that
    # the global top-k doesn't get exhausted by other users' memories before
    # the per-session filter is applied.  20× gives enough headroom in practice.
    fetch_count = limit * 20 if session_id else limit
    result = _get_client().rpc(
        "match_agent_memory",
        {"query_embedding": embedding, "match_count": fetch_count},
    ).execute()

    rows: list[dict] = result.data or []
    if session_id:
        rows = [r for r in rows if r["session_id"] == session_id]
    return rows[:limit]
