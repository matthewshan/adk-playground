"""LLM backend selection for the daily-briefing agent.

`make_model()` returns whatever the ADK `Agent(model=...)` constructor expects:
a string for Gemini (handled natively by ADK) or a `LiteLlm` instance for
Ollama and GitHub Models (routed through LiteLLM).

Backends are chosen via the `BACKEND` env var: `gemini` (default), `ollama`,
or `github`. Each branch is isolated in its own helper so adding a fourth
provider stays a small change.
"""

import os

from google.adk.models.lite_llm import LiteLlm


def make_model():
    """Return the model the ADK Agent should use, based on `BACKEND`."""
    backend = os.getenv("BACKEND", "gemini").lower()
    if backend == "ollama":
        return _ollama()
    if backend == "github":
        return _github_models()
    return _gemini()


def _gemini():
    return os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


def _ollama():
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    return LiteLlm(model=f"ollama_chat/{model}")


def _github_models():
    # LiteLLM's "github/" provider hits GitHub Models, GitHub's official
    # OpenAI-compatible inference endpoint. Auth: GITHUB_API_KEY (a PAT with
    # `models:read` scope). LiteLLM strips company prefixes — pass the bare
    # model name (e.g. "gpt-4.1"), not "openai/gpt-4.1".
    model = os.getenv("GITHUB_MODEL", "gpt-4.1")
    return LiteLlm(model=f"github/{model}")
