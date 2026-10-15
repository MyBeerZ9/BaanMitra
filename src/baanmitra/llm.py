"""LLM + ASR on free tiers only.

- LLM : Groq free tier (OpenAI-compatible), fallback to Google AI Studio.
- ASR : Groq whisper-large-v3 free tier.

No credit card is required by either provider.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import httpx

from .config import settings

_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


def _groq_headers() -> dict[str, str]:
    settings.require("groq_api_key")
    return {"Authorization": f"Bearer {settings.groq_api_key}"}


async def _post_with_retry(url: str, *, headers: dict[str, str], json_body: Any = None,
                           files: Any = None, data: Any = None,
                           retries: int = 3) -> httpx.Response:
    """Free-tier friendly retry with backoff (Groq returns 429 + retry-after)."""
    delay = 2.0
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(url, headers=headers, json=json_body,
                                      files=files, data=data)
                if r.status_code == 429:
                    time.sleep(delay)
                    delay *= 2
                    continue
                r.raise_for_status()
                return r
        except Exception as exc:  # network hiccup / rate limit
            last = exc
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"request failed after {retries} attempts: {last}")


# --------------------------------------------------------------------------- #
# chat
# --------------------------------------------------------------------------- #
async def chat(messages: list[dict[str, str]], *, json_mode: bool = False,
               temperature: float = 0.3) -> str:
    """OpenAI-compatible chat on the Groq free tier."""
    body: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    if settings.groq_api_key:
        r = await _post_with_retry(
            f"{settings.llm_base_url}/chat/completions",
            headers=_groq_headers(), json_body=body,
        )
        return r.json()["choices"][0]["message"]["content"]

    if settings.gemini_api_key:  # free AI Studio fallback
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}")
        r = await _post_with_retry(url, headers={}, json_body={
            "contents": [{"parts": [{"text": "\n".join(
                m["content"] for m in messages)}]}]
        })
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    raise RuntimeError(
        "No free LLM configured. Add GROQ_API_KEY (free, no card) to .env."
    )


async def chat_json(messages: list[dict[str, str]], **kw: Any) -> dict[str, Any]:
    raw = await chat(messages, json_mode=True, **kw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1])


# --------------------------------------------------------------------------- #
# task-specific helpers
# --------------------------------------------------------------------------- #
async def reason_threshold(event_summary: str) -> dict[str, Any]:
    """Is this a real, new, actionable flood risk? (LLM overrides the rule engine.)"""
    return await chat_json([
        {"role": "system", "content":
         "You are a flood-risk triage assistant for the Assam State Disaster Management "
         "context. Be conservative: false alarms destroy public trust. Reply with JSON: "
         "{\"significant\": bool, \"severity\": \"low|moderate|high|very_high\", "
         "\"reason\": \"one sentence\", \"lead_time_h\": number}"},
        {"role": "user", "content": event_summary},
    ])


async def compose_script(language: str, event_summary: str) -> str:
    """Write the spoken alert in the household's own language."""
    return await chat([
        {"role": "system", "content":
         f"You write spoken flood alerts for villagers in Assam, in {language}. "
         "Rules: 3-4 short sentences. Say which river, how high above danger level, "
         "when the water is expected, and one clear action (move to higher ground / "
         "the relief camp). Name ASDMA and CWC as the source. No markdown, no lists - "
         "this text is spoken aloud by a text-to-speech engine."},
        {"role": "user", "content": event_summary},
    ])


async def extract_ticket(transcript: str) -> dict[str, Any]:
    """Turn a villager's spoken distress message into a structured relief ticket."""
    return await chat_json([
        {"role": "system", "content":
         "You convert Assamese/Bengali/Hindi/English distress messages about Assam floods "
         "into a JSON relief ticket: {\"intent\": \"rescue|shelter|food|medical|info|other\", "
         "\"location_text\": \"village or circle\", \"severity\": \"low|medium|high|critical\", "
         "\"needs\": [\"boat\",\"medicine\",...], \"people_count\": number|null}"},
        {"role": "user", "content": transcript},
    ])


async def answer_understood(transcript: str) -> dict[str, Any]:
    """Did the household understand the alert, and do they need help?"""
    return await chat_json([
        {"role": "system", "content":
         "The caller was asked: 'did you understand, and do you need help?'. From their "
         "reply return JSON: {\"understood\": bool, \"needs_help\": bool, "
         "\"notes\": \"short phrase\"}"},
        {"role": "user", "content": transcript},
    ])


# --------------------------------------------------------------------------- #
# speech to text (Groq whisper-large-v3, free tier)
# --------------------------------------------------------------------------- #
async def transcribe(path: str, language: str = "") -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "rb") as fh:
        files = {"file": (os.path.basename(path), fh, "audio/mpeg")}
        data: dict[str, str] = {"model": settings.stt_model}
        if language:
            data["language"] = language
        r = await _post_with_retry(
            f"{settings.llm_base_url}/audio/transcriptions",
            headers=_groq_headers(), files=files, data=data,
        )
    return r.json().get("text", "").strip()
