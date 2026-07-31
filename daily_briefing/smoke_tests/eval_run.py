"""Offline eval — runs the agent over a Langfuse dataset and scores each output.

Use this to regression-test prompt, model, or backend changes: run it once per
variant and compare the runs side by side in the Langfuse UI.

    python3 daily_briefing/smoke_tests/eval_run.py            # run the experiment
    python3 daily_briefing/smoke_tests/eval_run.py --seed     # create/refresh the dataset

Requires LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL.
The run name defaults to the backend + model so variants are self-labelling.

The evaluators here are deterministic heuristics — they catch the failures that
actually bite (missing sections, tool errors leaking into the digest, truncated
output). Subjective quality is better handled by an LLM-as-a-judge evaluator
configured in the Langfuse UI, which also scores production traces.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from daily_briefing.telemetry import configure_telemetry  # noqa: E402

# Instrument before importing the agent — see daily_briefing/telemetry.py.
configure_telemetry()

from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions.in_memory_session_service import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402
from langfuse import get_client  # noqa: E402
from langfuse.experiment import Evaluation  # noqa: E402

from daily_briefing.agent import make_agent, now_et  # noqa: E402

DATASET_NAME = "daily-briefing-inputs"
APP_NAME = "daily_briefing_eval"
USER_ID = "eval"

# Keep the eval agent and its memory scope out of production.
eval_agent = make_agent(name=APP_NAME)

# Each item pairs a prompt with the sections its answer must mention.
# `expected_sections` drives the coverage evaluator, not an exact-match check —
# the briefing is free-form prose and live data changes daily.
_ITEMS = [
    {
        "name": "full-morning-digest",
        "input": (
            "Fetch weather for Grand Rapids MI, top news plus the latest cloud "
            "and AI news, NFL/MLB/CFL scores (highlight Detroit Lions, Toronto "
            "Blue Jays, Hamilton Tiger-Cats), and today's calendar events. "
            "Write the morning digest."
        ),
        "expected_sections": ["weather", "news", "sport", "calendar"],
    },
    {
        "name": "weather-only",
        "input": "What's the weather in Grand Rapids MI today?",
        "expected_sections": ["weather"],
    },
    {
        "name": "tracked-teams-scores",
        "input": "How did the Detroit Lions and Toronto Blue Jays do recently?",
        "expected_sections": ["lions", "blue jays"],
    },
    {
        "name": "untracked-team",
        "input": "What's the latest score for the Chicago Cubs?",
        "expected_sections": ["cubs"],
    },
    {
        "name": "ai-news",
        "input": "Give me the latest AI and cloud news headlines.",
        "expected_sections": ["ai"],
    },
    {
        "name": "calendar-today",
        "input": "What's on my calendar today?",
        "expected_sections": ["calendar"],
    },
]

# Substrings that mean a tool failed and the model surfaced the failure verbatim.
_ERROR_MARKERS = ("unavailable:", "traceback", "error:", "exception")


def seed_dataset() -> None:
    """Create the dataset and upsert its items (idempotent by item id)."""
    client = get_client()
    client.create_dataset(
        name=DATASET_NAME,
        description="Representative daily-briefing prompts for regression evals.",
    )
    for item in _ITEMS:
        client.create_dataset_item(
            dataset_name=DATASET_NAME,
            id=item["name"],  # stable id → re-seeding updates instead of duplicating
            input={"prompt": item["input"]},
            expected_output={"sections": item["expected_sections"]},
        )
    print(f"Seeded {len(_ITEMS)} items into '{DATASET_NAME}'")


async def _run_agent(prompt: str) -> str:
    """Run one agent turn and return the concatenated text output."""
    runner = Runner(
        agent=eval_agent,
        app_name=APP_NAME,
        session_service=InMemorySessionService(),
        artifact_service=InMemoryArtifactService(),
    )
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    chunks: list[str] = []
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=f"Current date and time: {now_et()}\n\n{prompt}")],
        ),
    ):
        if event.content:
            for part in event.content.parts or []:
                # Reasoning models emit thoughts as parts — exclude them from the answer.
                if part.text and not getattr(part, "thought", False):
                    chunks.append(part.text)
    return "\n".join(chunks)


def task(*, item, **_):
    """Experiment task — Langfuse calls this once per dataset item."""
    return asyncio.run(_run_agent(item.input["prompt"]))


def section_coverage(*, output, expected_output, **_):
    """Fraction of the expected sections that appear in the output."""
    sections = (expected_output or {}).get("sections", [])
    if not sections:
        return Evaluation(name="section_coverage", value=1.0, comment="no sections expected")
    text = (output or "").lower()
    hits = [s for s in sections if s.lower() in text]
    missing = [s for s in sections if s.lower() not in text]
    return Evaluation(
        name="section_coverage",
        value=len(hits) / len(sections),
        comment="all sections present" if not missing else f"missing: {', '.join(missing)}",
    )


def no_tool_errors(*, output, **_):
    """Flags tool failure text leaking into the user-facing briefing."""
    text = (output or "").lower()
    found = [m for m in _ERROR_MARKERS if m in text]
    return Evaluation(
        name="no_tool_errors",
        value=not found,
        data_type="BOOLEAN",
        comment="clean" if not found else f"error markers: {', '.join(found)}",
    )


def substantive(*, output, **_):
    """Guards against empty or truncated responses."""
    n = len((output or "").strip())
    return Evaluation(
        name="substantive",
        value=n >= 200,
        data_type="BOOLEAN",
        comment=f"{n} chars",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true", help="create/refresh the dataset, then exit")
    parser.add_argument("--run-name", default=None, help="label for this experiment run")
    args = parser.parse_args()

    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        print("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set — nothing to do.")
        return 1

    client = get_client()
    if not client.auth_check():
        print(f"Cannot reach Langfuse at {os.getenv('LANGFUSE_BASE_URL', 'cloud')}.")
        return 1

    if args.seed:
        seed_dataset()
        return 0

    backend = os.getenv("BACKEND", "gemini")
    model = os.getenv(f"{backend.upper()}_MODEL", "default")
    run_name = args.run_name or f"{backend}-{model}"

    dataset = client.get_dataset(DATASET_NAME)
    result = dataset.run_experiment(
        name="daily-briefing regression",
        run_name=run_name,
        description=f"backend={backend} model={model}",
        task=task,
        evaluators=[section_coverage, no_tool_errors, substantive],
        # The agent wakes the gaming PC and hits rate-limited APIs — serial is safer.
        max_concurrency=1,
        metadata={"backend": backend, "model": model},
    )

    client.flush()
    print(result.format())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
