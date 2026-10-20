"""Thin wrapper around any OpenAI-compatible chat completions API.

Defaults to Google Gemini's OpenAI-compatible endpoint (free tier available).
Point LLM_BASE_URL / LLM_MODEL at OpenAI, Azure OpenAI, Groq, a local Ollama
server, etc. without changing code.
"""
import os
import time

from openai import OpenAI

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-3.8-flash"


class LLMClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.client = OpenAI(
            api_key=api_key or os.environ["LLM_API_KEY"],
            base_url=base_url or os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        )

    def complete(self, messages: list[dict], temperature: float = 0.0) -> str:
        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=temperature)
                return resp.choices[0].message.content or ""
            except Exception:  # rate limits on free tiers are common; back off and retry
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        return ""
