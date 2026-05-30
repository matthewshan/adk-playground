"""Supabase-backed ADK memory service.

Implements BaseMemoryService so it can be plugged directly into the ADK Runner:

    runner = Runner(
        agent=root_agent,
        session_service=InMemorySessionService(),
        memory_service=SupabaseMemoryService(),
        ...
    )

The runner exposes a built-in ``LoadMemoryTool`` to the agent for on-demand
semantic search; persistence is handled automatically via the agent's
``after_agent_callback`` (see ``agent.py``).

Memory is scoped per ``app_name/user_id`` using the existing ``session_id`` column.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types
from google.genai.types import EmbedContentConfig
from typing_extensions import override

from daily_briefing.apis.supabase import insert_memory, similarity_search

logger = logging.getLogger(__name__)

# gemini-embedding-001 natively outputs 3072 dims, but pgvector's IVFFlat/HNSW
# indexes cap at 2000.  We truncate to 1536 (still excellent quality).
_EMBED_MODEL = "gemini-embedding-001"
_EMBED_DIMS = 1536


def _embed(text: str) -> list[float]:
    """Return a 1536-dimensional embedding for *text* using Google's embedding model."""
    from google import genai  # local import avoids circular deps at module load

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    result = client.models.embed_content(
        model=_EMBED_MODEL,
        contents=text,
        config=EmbedContentConfig(output_dimensionality=_EMBED_DIMS),
    )
    return result.embeddings[0].values

if TYPE_CHECKING:
    from google.adk.sessions.session import Session


def _user_scope(app_name: str, user_id: str) -> str:
    """Stable key used as session_id in the agent_memory table."""
    return f"{app_name}/{user_id}"


class SupabaseMemoryService(BaseMemoryService):
    """ADK memory service backed by Supabase pgvector.

    add_session_to_memory — embeds each agent text turn and writes to Supabase.
    search_memory         — embeds the query and returns kNN results.
    """

    def __init__(self) -> None:
        super().__init__()
        # One-line cause when the last search_memory failed; bot reads/clears it.
        self.last_search_error: str | None = None

    @override
    async def add_session_to_memory(self, session: "Session") -> None:
        """Embed and persist agent text turns from a completed session."""
        scope = _user_scope(session.app_name, session.user_id)

        for event in session.events:
            if not event.content or not event.content.parts:
                continue

            # Only persist model (agent) outputs — user messages and tool
            # call/result noise aren't worth storing long-term.
            # Use content.role instead of event.author so this works even when
            # agent.name differs from app_name.
            if event.content.role != "model":
                continue

            text = " ".join(
                part.text for part in event.content.parts if part.text
            ).strip()
            if not text:
                continue

            # _embed and insert_memory are synchronous (blocking HTTP).
            # Run them in a thread pool so they don't block the event loop.
            embedding = await asyncio.to_thread(_embed, text)
            await asyncio.to_thread(insert_memory, session_id=scope, content=text, embedding=embedding)

    @override
    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        """Semantic search over past sessions for this app/user.

        Best-effort: on embedding/DB failure, log + record the cause and return
        no results so the turn doesn't crash.
        """
        scope = _user_scope(app_name, user_id)
        try:
            # Both calls are synchronous (blocking HTTP) — offload to thread pool.
            embedding = await asyncio.to_thread(_embed, query)
            rows = await asyncio.to_thread(similarity_search, embedding=embedding, session_id=scope, limit=5)
        except Exception as exc:
            cause = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
            self.last_search_error = f"{type(exc).__name__}: {cause}" if cause else type(exc).__name__
            logger.error(
                "search_memory failed for %s; answering without memory: %s",
                scope,
                self.last_search_error,
                exc_info=True,
            )
            return SearchMemoryResponse(memories=[])

        memories = [
            MemoryEntry(
                id=str(row["id"]),
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=row["content"])],
                ),
            )
            for row in rows
        ]
        return SearchMemoryResponse(memories=memories)
