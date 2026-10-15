"""Speech-to-text on the Groq free tier (whisper-large-v3).

Free limits (verified Oct 2026): 20 requests/minute, 2,000 requests/day,
7,200 audio-seconds/hour (~8 hours of audio per day). No credit card.

Local fallback: whisper.cpp (MIT) - unlimited, offline, slower.
"""
from __future__ import annotations

import logging
import os

from .. import llm

log = logging.getLogger("baanmitra.stt")


async def transcribe(path: str, language: str = "") -> str:
    """Transcribe an audio file, preferring the free Groq endpoint."""
    try:
        text = await llm.transcribe(path, language=language)
        if text:
            log.info("STT (groq %s): %s", settings_stt(), text[:80])
            return text
    except Exception as exc:
        log.warning("Groq STT unavailable (%s); trying local whisper.cpp", exc)

    local = _whisper_cpp(path)
    if local:
        return local
    raise RuntimeError("transcription failed - check GROQ_API_KEY (free tier).")


def settings_stt() -> str:
    from ..config import settings
    return settings.stt_model


def _whisper_cpp(path: str) -> str:
    exe = os.path.join("external", "whisper.cpp", "main")
    model = os.path.join("external", "whisper.cpp", "models", "ggml-base.bin")
    if not (os.path.exists(exe) and os.path.exists(model)):
        log.info("whisper.cpp not installed; skipping local fallback")
        return ""
    import subprocess
    out = path + ".txt"
    try:
        subprocess.run(
            [exe, "-m", model, "-f", path, "-otxt", "-of", path[:-len(".mp3")]],
            check=True, capture_output=True, timeout=300,
        )
        if os.path.exists(out):
            return open(out, encoding="utf-8").read().strip()
    except Exception as exc:
        log.warning("whisper.cpp failed: %s", exc)
    return ""
