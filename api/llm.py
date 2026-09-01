"""LLM client for the conversational agent.

Both Groq and Gemini expose an OpenAI-compatible chat-completions endpoint
(including tool/function calling), so a single `openai.OpenAI` client covers
either provider — only the base_url, api_key and model name change. Pick the
provider with LLM_PROVIDER=groq|gemini in .env; the first one with a key set
wins if LLM_PROVIDER is unset.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import HTTPException
from openai import OpenAI

load_dotenv()

_PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "default_model": "openai/gpt-oss-120b",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "default_model": "gemini-3.6-flash",
    },
}


def _select_provider() -> str:
    requested = os.getenv("LLM_PROVIDER", "").strip().lower()
    if requested in _PROVIDERS:
        return requested
    for name, cfg in _PROVIDERS.items():
        if os.getenv(cfg["key_env"]):
            return name
    return "groq"


@lru_cache(maxsize=1)
def get_llm() -> tuple[OpenAI, str]:
    """Returns (client, model_name) for the configured provider. Cached — one
    client per process. Raises 503 (not 500) when no key is configured, since
    this is a missing-config problem, not a server bug."""
    provider = _select_provider()
    cfg = _PROVIDERS[provider]
    api_key = os.getenv(cfg["key_env"])
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=f"Agent IA indisponible : {cfg['key_env']} n'est pas configurée (voir .env.example).",
        )
    model = os.getenv("LLM_MODEL") or cfg["default_model"]
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"], timeout=30.0, max_retries=1)
    return client, model
