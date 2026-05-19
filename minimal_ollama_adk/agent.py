import os

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm


MODEL_NAME = os.getenv("OLLAMA_MODEL", "smollm2:135m")


root_agent = Agent(
    name="minimal_ollama_adk",
    model=LiteLlm(model=f"ollama_chat/{MODEL_NAME}"),
    description="A very small ADK smoke-test agent backed by local Ollama.",
    instruction=(
        "You are a concise local test assistant. "
        "Keep replies short. If the user asks for an exact string, return that exact string."
    ),
)
