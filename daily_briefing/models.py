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


def supports_google_search() -> bool:
    """True only on Gemini; google_search is a native-Gemini tool (ADK raises otherwise)."""
    return os.getenv("BACKEND", "gemini").lower() == "gemini"


# GitHub Models' free tier rejects request bodies larger than this for gpt-4.1.
_GITHUB_MODELS_TOKEN_LIMIT = 8000


def request_token_limit() -> int | None:
    """Per-request token cap for the active backend, or None if effectively unbounded.

    GitHub Models' free tier caps gpt-4.1 request bodies at 8000 tokens; Gemini
    and local Ollama have ample context, so they return None (no trimming).
    """
    if os.getenv("BACKEND", "gemini").lower() == "github":
        return _GITHUB_MODELS_TOKEN_LIMIT
    return None


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
