"""Escalation policy for unanswered flood-alert calls.

When Twilio reports no-answer / busy / failed we count the attempt in Redis
(free Upstash tier; falls back to an in-memory counter if Redis is not
configured) and escalate after ESCALATION_ATTEMPTS.

Escalation ladder:
    attempt 1  -> retry with exponential backoff
    attempt 2  -> retry again
    attempt 3  -> SMS the household's gaon-bura / volunteer
                 + write an escalation row for the DDMA control room
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .. import db
from ..config import settings

log = logging.getLogger("baanmitra.escalation")

_redis = None
_mem: dict[str, int] = {}


def _r():
    global _redis
    if _redis is None:
        if settings.redis_url:
            try:
                import redis
                _redis = redis.from_url(settings.redis_url, decode_responses=True)
                _redis.ping()
                return _redis
            except Exception as exc:
                log.warning("Upstash Redis unavailable (%s); using memory", exc)
        _redis = False
    return _redis or None


def attempts(call_sid: str, bump: bool = False) -> int:
    key = f"baanmitra:attempts:{call_sid}"
    client = _r()
    if client:
        if bump:
            n = client.incr(key)
            client.expire(key, 86400)
            return int(n)
        return int(client.get(key) or 0)
    if bump:
        _mem[key] = _mem.get(key, 0) + 1
    return _mem.get(key, 0)


async def handle_call_outcome(call_sid: str, status: str) -> None:
    """Called from the Twilio Status Callback."""
    call = db.get_call_by_sid(call_sid)
    if not call:
        log.info("status callback for unknown sid %s (%s)", call_sid, status)
        return

    if status == "completed":
        db.update_call_by_sid(call_sid, status="answered")
        return

    if status in ("no-answer", "busy", "failed", "canceled"):
        n = attempts(call_sid, bump=True)
        log.info("call %s attempt %s failed (%s)", call_sid[:8], n, status)

        if n >= settings.escalation_attempts:
            db.update_call_by_sid(call_sid, status="escalated")
            _notify(call)
        else:
            db.update_call_by_sid(call_sid, status="no_answer", attempts=n)
            # A retry is scheduled by the next ingest cycle (GitHub Actions cron).


def _notify(call: dict) -> None:
    from ..voice import telephony

    notified: list[str] = []
    gaon_bura = os.getenv("GAON_BURA_%s" % call.get("household_id", ""), "")
    if gaon_bura:
        try:
            telephony.send_sms(gaon_bura,
                               "Unreachable household in a flood-warning zone. "
                               "Please check on them physically. Helpline 1079. "
                               "(BaanMitra, using ASDMA/CWC data)")
            notified.append(gaon_bura)
        except Exception as exc:
            log.warning("gaon-bura SMS failed: %s", exc)

    db.save_escalation(call["id"], call.get("household_id", ""),
                       "no answer after retries", notified)
    log.info("escalated call %s (notified %d)", call["id"][:8], len(notified))
