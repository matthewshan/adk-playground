#!/usr/bin/env python3
"""Smoke-test for Supabase pgvector memory tools.

Tests the full stack: embedding generation → insert → similarity search.

Run from the repo root:
    python daily_briefing/smoke_tests/test_memory.py

Requires in daily_briefing/.env:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    GEMINI_API_KEY
"""

from __future__ import annotations

import io
import sys
import traceback

# Ensure UTF-8 output on Windows terminals that default to cp1252.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import uuid
from pathlib import Path

# Resolve repo root regardless of where the script is invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import os

from daily_briefing.apis.supabase import _get_client, insert_memory, similarity_search
from daily_briefing.memory.supabase_memory_service import _embed

PASS = "✓ PASS"
FAIL = "✗ FAIL"
SKIP = "– SKIP"

# Unique session ID per run — isolates test rows from real data.
_SESSION_ID = f"smoke-test-{uuid.uuid4()}"

# Three semantically distinct memories for the kNN test.
_KNN_MEMORIES = [
    "I love hiking and outdoor adventures in the mountains",
    "My favourite food is sushi, especially salmon nigiri",
    "I prefer Python over JavaScript for backend development",
]
_KNN_QUERY = "What do I like to eat?"
_KNN_EXPECTED_KEYWORD = "sushi"


def _header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _check_env() -> bool:
    """Return True if all required env vars are set; print a skip message otherwise."""
    missing = [
        v
        for v in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY")
        if not os.getenv(v)
    ]
    if missing:
        print(
            f"{SKIP}  Missing env var(s): {', '.join(missing)}"
            " — add them to daily_briefing/.env to run memory tests"
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_1_connectivity() -> bool | None:
    _header("MEMORY 1 — Supabase connectivity")
    if not _check_env():
        return None
    try:
        client = _get_client()
        # A lightweight query: fetch zero rows just to confirm credentials + table exist.
        result = client.table("agent_memory").select("id").limit(1).execute()
        print(f"  agent_memory table reachable — {len(result.data)} row(s) sampled")
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


def test_2_store_and_retrieve() -> bool | None:
    _header("MEMORY 2 — store and retrieve round-trip")
    if not _check_env():
        return None
    content = "The user's favourite colour is blue"
    try:
        # Write directly via insert_memory (same path LoadMemoryTool uses).
        embedding = _embed(content)
        insert_memory(session_id=_SESSION_ID, content=content, embedding=embedding)
        print(f"  insert_memory() → stored {len(content)} chars")

        # Read back directly from the DB so we're not just trusting the tool.
        client = _get_client()
        result = (
            client.table("agent_memory")
            .select("session_id, content")
            .eq("session_id", _SESSION_ID)
            .execute()
        )
        rows = result.data or []
        assert rows, "No rows found in agent_memory for this session_id"
        stored_content = rows[0]["content"]
        assert stored_content == content, (
            f"Content mismatch: expected {content!r}, got {stored_content!r}"
        )
        print(f"  DB confirms row present: {stored_content!r}")
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


def test_3_vector_similarity_knn() -> bool | None:
    _header("MEMORY 3 — vector similarity / kNN ordering")
    if not _check_env():
        return None
    try:
        # Insert three semantically distinct memories.
        for mem in _KNN_MEMORIES:
            embedding = _embed(mem)
            insert_memory(session_id=_SESSION_ID, content=mem, embedding=embedding)
            print(f"  stored: {mem[:60]}")

        # Search using raw similarity_search so we can inspect floats directly.
        query_embedding = _embed(_KNN_QUERY)
        rows = similarity_search(
            embedding=query_embedding,
            session_id=_SESSION_ID,
            limit=len(_KNN_MEMORIES),
        )

        print(f"\n  Query: {_KNN_QUERY!r}")
        print(f"  Results ({len(rows)} row(s)):")
        for i, row in enumerate(rows, start=1):
            sim_pct = round(row["similarity"] * 100, 1)
            print(f"    {i}. [{sim_pct}%] {row['content']}")

        assert rows, "No results returned from similarity_search"

        top_result = rows[0]["content"]
        assert _KNN_EXPECTED_KEYWORD in top_result.lower(), (
            f"Expected top result to contain {_KNN_EXPECTED_KEYWORD!r}, "
            f"but got: {top_result!r}"
        )

        top_similarity = rows[0]["similarity"]
        assert top_similarity > 0.5, (
            f"Top similarity score {top_similarity:.3f} is suspiciously low — "
            "check embedding model or DB schema"
        )

        print(f"\n  Top match is food-related ✓  (similarity={top_similarity:.3f})")
        print(PASS)
        return True
    except Exception:
        print(FAIL)
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


def teardown() -> None:
    """Delete all rows written by this test run."""
    try:
        client = _get_client()
        result = (
            client.table("agent_memory")
            .delete()
            .eq("session_id", _SESSION_ID)
            .execute()
        )
        deleted = len(result.data) if result.data else "?"
        print(f"\n  Cleaned up {deleted} test row(s) for session {_SESSION_ID!r}")
    except Exception:
        print("  WARNING: teardown failed — test rows may remain in the DB")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print(f"Session ID for this run: {_SESSION_ID}")

    tests = [test_1_connectivity, test_2_store_and_retrieve, test_3_vector_similarity_knn]
    results = [t() for t in tests]

    passed = results.count(True)
    failed = results.count(False)
    skipped = results.count(None)

    print(f"\n{'─' * 60}")
    print(f"Results: {passed}/{len(results) - skipped} passed, {skipped} skipped")

    if not all(r is None for r in results):
        # Only prompt if at least one test actually ran (i.e. credentials were present).
        print(
            f"\n  Test rows are still in Supabase under session_id={_SESSION_ID!r}."
            "\n  You can inspect them now before they are deleted."
        )
        try:
            input("\n  Press Enter to delete test rows and exit... ")
        except EOFError:
            # Non-interactive mode (e.g. piped stdin) — skip the pause.
            print("  (non-interactive mode — skipping pause)")
        teardown()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
