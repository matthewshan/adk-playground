import asyncio

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from daily_briefing.agent import root_agent

APP_NAME = "daily_briefing"
USER_ID = "scheduler"


async def run() -> None:
    load_dotenv()
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    "Fetch weather for Grand Rapids MI, top news plus the latest cloud "
                    "and AI news, NFL/MLB/CFL scores (highlight Detroit Lions, Toronto "
                    "Blue Jays, Hamilton Tiger-Cats), and today's calendar events. "
                    "Write and send the morning digest."
                )
            ],
        ),
    ):
        if event.content:
            for part in event.content.parts or []:
                if part.text:
                    print(part.text)


if __name__ == "__main__":
    asyncio.run(run())
