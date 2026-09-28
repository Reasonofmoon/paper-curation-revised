"""Gemini text calls for review, timeline narrative, and category summaries.

Used only when ``llm.provider`` is ``gemini`` (config.json or
``PAPER_CURATION_LLM_PROVIDER``). The default provider stays Anthropic, so
existing topics are unchanged.

This module never embeds a key in source. ``GOOGLE_API_KEY`` /
``GEMINI_API_KEY`` (or config.json ``google_api_key``) is read at call time.
If the key is missing, every function raises ``GeminiKeyMissing`` before any
network request.

Cost-efficient default model: ``gemini-2.5-flash``.
"""
from __future__ import annotations

import json


class GeminiKeyMissing(RuntimeError):
    """Raised when a Gemini call was requested and no API key is configured."""


def require_google_key() -> str:
    """Return the Google key or raise before any HTTP call."""
    from config_loader import get_google_key

    key = (get_google_key() or "").strip()
    if not key:
        raise GeminiKeyMissing(
            "GOOGLE_API_KEY/GEMINI_API_KEY is not set (env or config.json). "
            "Refusing to call Gemini."
        )
    return key


def _client(api_key: str):
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed. Run: pip install google-genai"
        ) from exc
    return genai.Client(api_key=api_key)


def _record(resp, model: str) -> None:
    try:
        import usage_log
        usage_log.record_gemini(resp, model)
    except Exception:
        return


def gemini_generate_text(prompt: str, *, model: str, max_output_tokens: int = 4000,
                         temperature: float = 0.4) -> str:
    """Plain-text Gemini completion. Raises GeminiKeyMissing if no key."""
    api_key = require_google_key()
    from google.genai import types

    client = _client(api_key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    _record(resp, model)
    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        raise RuntimeError(f"Gemini returned empty text (model={model})")
    return text


def _schema_for_gemini(schema: dict) -> dict:
    """Drop JSON Schema keywords the Gemini response_schema subset rejects."""
    drop = {"minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems"}

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items() if k not in drop}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def gemini_generate_json(prompt: str, schema: dict, *, model: str,
                         max_output_tokens: int = 4000,
                         temperature: float = 0.2) -> dict:
    """Structured JSON Gemini completion. No network call when the key is absent."""
    api_key = require_google_key()
    from google.genai import types

    client = _client(api_key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_schema=_schema_for_gemini(schema),
        ),
    )
    _record(resp, model)
    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        raise RuntimeError(f"Gemini returned empty JSON (model={model})")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise RuntimeError("Gemini JSON response was not an object")
    return data
