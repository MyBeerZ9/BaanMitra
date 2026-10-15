"""FastAPI service: Twilio webhooks, cron hook, dashboard data, audio hosting.

Run:  python -m baanmitra.api.main      (then open /dashboard/)
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import db, llm
from ..agents import triager as triager_agent
from ..agents import watchdog
from ..config import settings

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("baanmitra.api")

app = FastAPI(title="BaanMitra API", version="1.0.0",
              description="Last mile of India's flood early warning - free tier build")


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "service": "baanmitra", "cost": "Rs 0"}


# --------------------------------------------------------------------------- #
# dashboard
# --------------------------------------------------------------------------- #
@app.get("/dashboard/data")
async def dashboard_data() -> JSONResponse:
    calls, tickets = [], []
    db_error = ""
    try:
        calls = db.recent_calls(limit=40)
        tickets = db.open_tickets(limit=40)
    except Exception as exc:  # no DATABASE_URL / Supabase asleep -> degrade, never crash
        db_error = str(exc)
    answered = sum(1 for c in calls if c.get("status") == "answered")
    escalated = sum(1 for c in calls if c.get("status") == "escalated")
    return JSONResponse({
        "calls": calls,
        "tickets": tickets,
        "db_error": db_error,
        "stats": {
            "total_calls": len(calls),
            "answered": answered,
            "escalated": escalated,
            "open_tickets": len(tickets),
            "reach_rate": round(answered / len(calls), 3) if calls else 0.0,
        },
    })


@app.get("/dashboard/", response_class=HTMLResponse)
async def dashboard_page() -> HTMLResponse:
    here = Path(__file__).resolve().parent.parent.parent.parent / "dashboard"
    index = here / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>dashboard/index.html not found</h1>")


@app.get("/audio/{name}")
async def audio(name: str) -> FileResponse:
    path = Path(settings.audio_dir) / name
    if not path.exists():
        return Response(status_code=404)
    media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
    return FileResponse(str(path), media_type=media)


# --------------------------------------------------------------------------- #
# cron (free GitHub Actions every 15 minutes)
# --------------------------------------------------------------------------- #
@app.post("/cron/ingest")
async def cron_ingest(token: str = "") -> JSONResponse:
    if token != settings.cron_token:
        return JSONResponse({"error": "bad token"}, status_code=401)
    result = await watchdog.run_once()
    return JSONResponse(result)


# --------------------------------------------------------------------------- #
# Twilio webhooks
# --------------------------------------------------------------------------- #
@app.post("/twilio/gather")
async def twilio_gather(SpeechResult: str = Form(""),
                        From: str = Form(""), CallSid: str = Form("")) -> Response:
    """Villager answered the alert - capture, understand, prioritise."""
    from ..voice import telephony as t

    if not SpeechResult.strip():
        return Response(t.escalation_twiml(), media_type="application/xml")

    try:
        verdict = await llm.answer_understood(SpeechResult)
    except Exception:
        verdict = {"understood": True, "needs_help": False, "notes": SpeechResult}

    db.update_call_by_sid(CallSid, status="answered", transcript=SpeechResult,
                          needs_help=bool(verdict.get("needs_help")))

    reply = ("আমাৰ সহায়্যৰ দল আপোনালৈ যোগাযোগ কৰিব। "
             "আপনি নিশ্চিন্ত থাকক।") if verdict.get("needs_help") else \
            ("ধন্যবাদ। অনুগ্ৰহ কৰি ওখ-ওখ স্তৰলৈ যাওক।")
    return Response(t.confirmation_twiml(f"{settings.public_base_url}/audio/placeholder"),
                    media_type="application/xml")


@app.post("/twilio/status")
async def twilio_status(CallSid: str = Form(""),
                        CallStatus: str = Form("")) -> JSONResponse:
    """Twilio Status Callback: answered / no-answer / busy / failed."""
    from .escalation import handle_call_outcome
    asyncio.create_task(handle_call_outcome(CallSid, CallStatus))
    return JSONResponse({"ok": True})


@app.post("/twilio/whatsapp")
async def twilio_whatsapp(From: str = Form(""), NumMedia: int = Form(0),
                         MediaUrl0: str = Form(""),
                         Body: str = Form("")) -> JSONResponse:
    """Inbound WhatsApp voice note from a villager after the flood."""
    import httpx

    phone = From.replace("whatsapp:", "")
    if MediaUrl0 and not settings.consented_numbers:
        return JSONResponse({"error": "no consented numbers configured"}, status_code=400)

    if MediaUrl0:
        path = Path(settings.audio_dir)
        path.mkdir(parents=True, exist_ok=True)
        local = path / f"in_{abs(hash(From)) % 10**8}.mp3"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(MediaUrl0)
            local.write_bytes(r.content)
        asyncio.create_task(triager_agent.handle_audio(str(local), phone))
        return JSONResponse({"queued": True})
    return JSONResponse({"queued": False})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
