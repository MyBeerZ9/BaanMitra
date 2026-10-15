"""Voice providers: free text-to-speech chain.

Order of preference (all free, none require a credit card):

1. BHASHINI_API_KEY   - Govt. of India national language mission, real Assamese /
                        Bodo / Bengali voices. Free with registration.
2. Local Indic-TTS    - AI4Bharat, MIT licence, runs offline on your laptop.
                        (Assamese, Bodo, Bengali, ... 13 languages.)
3. TTSFREE_API_KEY    - ttsfree.in free account, 200 credits/month, built on
                        AI4Bharat Indic Parler-TTS.
4. gTTS               - last resort, no key at all (Hindi/Bengali/English only).

Twilio's own <Say> has no Assamese voice, so the pipeline is always
TTS -> MP3 -> <Play>. That is how production IVR systems do it too.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx

from ..config import settings
from ..models import Language

log = logging.getLogger("baanmitra.tts")

# language enum -> provider codes
_BHASHINI_LANG = {"as": "as", "brx": "brx", "bn": "bn", "hi": "hi", "en": "en"}
_GTTS_LANG = {"as": "bn", "brx": "hi", "bn": "bn", "hi": "hi", "en": "en"}


def _cache_path(text: str, lang: str, ext: str = "mp3") -> Path:
    digest = hashlib.sha1(f"{lang}|{text}".encode("utf-8")).hexdigest()[:16]
    d = Path(settings.audio_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{lang}_{digest}.{ext}"


async def _bhashini(text: str, lang: str) -> Optional[bytes]:
    if not settings.bhashini_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
                headers={
                    "userID": settings.bhashini_user_id or settings.bhashini_api_key,
                    "ulcaApiKey": settings.bhashini_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "pipelineTasks": [{
                        "taskType": "tts",
                        "config": {
                            "language": {"sourceLanguage": _BHASHINI_LANG.get(lang, "as")},
                            "gender": "female",
                        },
                    }],
                    "inputData": {
                        "input": [{"source": text}],
                        "audio": [{}],
                    },
                },
            )
            if r.status_code != 200:
                log.warning("Bhashini returned %s", r.status_code)
                return None
            audio = (r.json().get("pipelineResponse") or [{}])[0].get("audioContent")
            if not audio:
                return None
            import base64
            return base64.b64decode(audio)
    except Exception as exc:
        log.warning("Bhashini TTS failed: %s", exc)
        return None


def _indic_tts(text: str, lang: str) -> Optional[bytes]:
    """Local AI4Bharat Indic-TTS (MIT). Requires the repo + torch; optional."""
    root = Path("external") / "Indic-TTS"
    model = root / "as" / "fastpitch" / "best_model.pth"
    if not model.exists():
        return None
    out = _cache_path(text, lang, "wav")
    cmd = [sys.executable, "-m", "TTS.bin.synthesize",
           "--text", text,
           "--model_path", str(root / lang / "fastpitch" / "best_model.pth"),
           "--config_path", str(root / lang / "config.json"),
           "--vocoder_path", str(root / lang / "hifigan" / "best_model.pth"),
           "--vocoder_config_path", str(root / lang / "hifigan" / "config.json"),
           "--out_path", str(out)]
    try:
        subprocess.run(cmd, cwd=root, check=True, capture_output=True, timeout=180)
        return out.read_bytes() if out.exists() else None
    except Exception as exc:
        log.warning("Indic-TTS failed: %s", exc)
        return None


async def _ttsfree(text: str, lang: str) -> Optional[bytes]:
    if not settings.ttsfree_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://ttsfree.in/api/v1/tts",
                headers={"Authorization": f"Bearer {settings.ttsfree_api_key}"},
                json={"text": text, "language": _BHASHINI_LANG.get(lang, "as"),
                      "format": "mp3"},
            )
            if r.status_code != 200:
                return None
            if r.headers.get("content-type", "").startswith("audio"):
                return r.content
            import base64
            return base64.b64decode(r.json().get("audio", ""))
    except Exception as exc:
        log.warning("ttsfree failed: %s", exc)
        return None


def _gtts(text: str, lang: str) -> Optional[bytes]:
    try:
        from gtts import gTTS
        import io
        buf = io.BytesIO()
        gTTS(text=text, lang=_GTTS_LANG.get(lang, "hi"), slow=False).write_to_fp(buf)
        return buf.getvalue()
    except Exception as exc:
        log.warning("gTTS failed: %s", exc)
        return None


async def synthesize(text: str, lang: Language | str) -> Path:
    """Return the path to an audio file containing `text` spoken in `lang`."""
    lang_code = lang.value if isinstance(lang, Language) else str(lang)
    if not text or not text.strip():
        raise ValueError("empty text")

    cached = _cache_path(text, lang_code)
    if cached.exists():
        return cached

    # NOTE: the chain mixes async providers (HTTP) and sync ones (local Indic-TTS,
    # gTTS), so each entry is only awaited if it actually returns an awaitable.
    import inspect

    for name, fn in (("bhashini", lambda: _bhashini(text, lang_code)),
                     ("indic-tts", lambda: _indic_tts(text, lang_code)),
                     ("ttsfree", lambda: _ttsfree(text, lang_code)),
                     ("gtts", lambda: _gtts(text, lang_code))):
        result = fn()
        if inspect.isawaitable(result):
            result = await result
        if result:
            cached.write_bytes(result)
            log.info("TTS via %s -> %s (%d bytes)", name, cached.name, len(result))
            return cached

    raise RuntimeError(
        "no free TTS provider produced audio. Configure one FREE provider: "
        "Bhashini (bhashini.gov.in) or Indic-TTS (MIT, local). See COSTS.md."
    )
