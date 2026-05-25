# Supabase Vector DB — Setup Guide

This document explains how to connect the `daily_briefing` agent (and other agents
in this repo) to a Supabase pgvector database for persistent memory and RAG. It
covers obtaining credentials, the one-time schema setup, and wiring a memory tool
into an ADK agent.

The Supabase project itself (`adk-agents-vector-db`) is managed separately in
[`cloud-infrastructure/supabase-vector-db`](https://github.com/matthewshan/cloud-infrastructure/tree/main/supabase-vector-db).

---

## 1. Get your credentials from the Supabase dashboard

Open [supabase.com/dashboard](https://supabase.com/dashboard), select the
`adk-agents-vector-db` project, and navigate to **Settings → API**.

| Value | Location | Environment variable |
|---|---|---|
| Project URL | Settings → API → **Project URL** | `SUPABASE_URL` |
| `service_role` key | Settings → API → **Project API keys** | `SUPABASE_SERVICE_ROLE_KEY` |
| Connection string | Settings → **Database** → Connection string → **URI** | schema setup only |

> **`service_role` key warning:** this key has full database access and bypasses
> all row-level security. Keep it in `.env` only — never commit it to git.

---

## 2. Auth — which key to use

Supabase provides two keys:

| Key | Access | Use for |
|---|---|---|
| `anon` | Scoped by Row Level Security | Client-side / user-authenticated flows |
| `service_role` | Full DB access, bypasses RLS | ADK agents and server-side tools ✓ |

For all agent tools in this repo use the `service_role` key — agents run
server-side and need cross-session read/write access.

---

## 3. One-time schema setup

Run the following SQL once using either the
**[Supabase SQL Editor](https://supabase.com/dashboard)** (project → **SQL Editor**
→ **New query**) or `psql` with the connection string from Section 1.

```sql
-- Enable pgvector (must run this first — it is not auto-enabled).
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop old objects if re-running after a dimension change.
DROP FUNCTION IF EXISTS match_agent_memory(vector, int);
DROP TABLE IF EXISTS agent_memory;

-- Create a table for ADK agent memory.
-- gemini-embedding-001 natively outputs 3072 dims, but pgvector's IVFFlat/HNSW
-- indexes cap at 2000. We configure output_dimensionality=1536 in the Python client.
CREATE TABLE agent_memory (
  id          bigserial    PRIMARY KEY,
  session_id  text         NOT NULL,
  content     text         NOT NULL,
  embedding   vector(1536),
  created_at  timestamptz  DEFAULT now()
);

-- HNSW index for approximate nearest-neighbour search.
-- Handles dynamic inserts correctly (unlike IVFFlat, which computes centroids at
-- creation time and requires a full reindex after bulk loads).
CREATE INDEX ON agent_memory USING hnsw (embedding vector_cosine_ops);

-- RPC function used by the Python memory tool for similarity search.
CREATE OR REPLACE FUNCTION match_agent_memory(
  query_embedding vector(1536),
  match_count     int DEFAULT 5
)
RETURNS TABLE (id bigint, session_id text, content text, similarity float)
LANGUAGE sql STABLE
AS $$
  SELECT   id, session_id, content,
           1 - (embedding <=> query_embedding) AS similarity
  FROM     agent_memory
  ORDER BY embedding <=> query_embedding
  LIMIT    match_count;
$$;
```

> **Model note:** `gemini-embedding-001` (successor to deprecated `text-embedding-004`)
> outputs 3072 dims natively, but pgvector's IVFFlat and HNSW indexes cap at 2000.
> We truncate to **1536** via `output_dimensionality` — still excellent quality.
> The Python client (`tools/memory.py`) sets this automatically.

---

## 4. Environment variables

Add these to `daily_briefing/.env` (copy from `.env.example` first if you haven't):

```dotenv
# Supabase vector DB — https://supabase.com/dashboard → Settings → API
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service_role_key>
```

---

## 5. Python memory tool

Install the dependency:

```bash
pip install supabase
```

Create `daily_briefing/tools/memory.py`:

```python
import os
from supabase import create_client, Client

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _client


def store_memory(session_id: str, content: str, embedding: list[float]) -> None:
    """Persist a text chunk and its embedding for a given session."""
    _get_client().table("agent_memory").insert(
        {"session_id": session_id, "content": content, "embedding": embedding}
    ).execute()


def search_memory(
    embedding: list[float], session_id: str | None = None, limit: int = 5
) -> list[dict]:
    """Return the top-k most similar memory entries, optionally filtered by session."""
    result = _get_client().rpc(
        "match_agent_memory",
        {"query_embedding": embedding, "match_count": limit},
    ).execute()

    rows = result.data or []
    if session_id:
        rows = [r for r in rows if r["session_id"] == session_id]
    return rows
```

Then import and register it in `daily_briefing/agent.py` alongside the existing tools.

---

## 6. `.env.example` reference

The full env file lives at `daily_briefing/.env.example`. After adding the Supabase
variables it should include:

```dotenv
# Supabase vector DB
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```
