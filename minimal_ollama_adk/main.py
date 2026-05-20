import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agent import root_agent


APP_NAME = "minimal_ollama_adk"
USER_ID = "local_user"


async def create_session() -> tuple[InMemoryRunner, str]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
    )
    return runner, session.id


async def run_prompt(runner: InMemoryRunner, session_id: str, prompt: str) -> str:
    last_text = ""
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        ),
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.text:
                last_text = part.text

    return last_text


async def interactive_loop() -> int:
    runner, session_id = await create_session()

    print("Interactive mode. Type a prompt and press Enter.")
    print("Type 'exit' or 'quit' to stop.")

    while True:
        try:
            prompt = input("prompt> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        if not prompt:
            continue

        if prompt.lower() in {"exit", "quit"}:
            return 0

        response = await run_prompt(runner, session_id, prompt)
        print(response)


def main() -> int:
    load_dotenv(Path(__file__).parent / ".env")

    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        return asyncio.run(interactive_loop())

    runner, session_id = asyncio.run(create_session())
    response = asyncio.run(run_prompt(runner, session_id, prompt))
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())