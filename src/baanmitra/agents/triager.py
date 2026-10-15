"""AGENT B · TRIAGER - the inbound distress-triage agent.

WhatsApp voice note (free Twilio sandbox) -> Whisper STT -> LLM extraction ->
structured relief ticket -> dashboard.

Usage:
    python -m baanmitra.agents.triager <audio_file> [+91...]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Optional

from .. import db, llm
from ..models import Ticket
from ..voice import stt

log = logging.getLogger("baanmitra.triager")

_FALLBACK = {"intent": "other", "location_text": "", "severity": "medium",
             "needs": [], "people_count": None}


async def handle_audio(path: str, phone: str, language: str = "") -> Ticket:
    transcript = await stt.transcribe(path, language=language)
    if not transcript:
        raise RuntimeError("empty transcript")

    try:
        data = await llm.extract_ticket(transcript)
    except Exception as exc:
        log.warning("LLM extraction unavailable (%s) - storing raw ticket", exc)
        data = {}

    merged = {**_FALLBACK, **(data or {})}
    ticket = Ticket(
        phone=phone,
        transcript=transcript,
        intent=str(merged.get("intent", "other")),
        location_text=str(merged.get("location_text", "")),
        severity=str(merged.get("severity", "medium")),
        needs=list(merged.get("needs") or []),
        people_count=merged.get("people_count"),
        source="whatsapp",
    )
    db.save_ticket(ticket)
    log.info("ticket %s: intent=%s severity=%s needs=%s",
             ticket.id[:8], ticket.intent, ticket.severity, ticket.needs)
    return ticket


def _cli() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    ap = argparse.ArgumentParser(description="BaanMitra TRIAGER agent")
    ap.add_argument("audio", nargs="?", help="path to an audio note (mp3/wav/ogg)")
    ap.add_argument("phone", nargs="?", default="", help="caller number in E.164")
    args = ap.parse_args()

    if not args.audio:
        print("usage: python -m baanmitra.agents.triager <audio-file> [+91...]")
        return
    if not os.path.exists(args.audio):
        raise SystemExit(f"file not found: {args.audio}")
    ticket = asyncio.run(handle_audio(args.audio, args.phone or "unknown"))
    print(ticket.model_dump_json(indent=2))


if __name__ == "__main__":
    _cli()
