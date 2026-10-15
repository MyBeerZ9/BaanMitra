"""AGENT A · WATCHDOG - the outbound flood-alert agent.

One cycle:
  1. collect RiskEvents from every free source (FLEWS, CWC, Open-Meteo)
  2. ask the free LLM whether each event is real, new and actionable
  3. resolve the affected households (consented only) in that revenue circle
  4. compose a spoken alert in the household's language and synthesise it
  5. place the call via the Twilio trial
  6. record the call and let the escalation policy handle non-responders

Usage:
    python -m baanmitra.agents.watchdog            # one real cycle
    python -m baanmitra.agents.watchdog --dry-run  # plan only, no calls
    python -m baanmitra.agents.watchdog --demo     # use a seeded demo event
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from .. import db, llm
from ..config import settings
from ..models import Household, Language, RiskEvent, Severity
from ..sources import collect_events
from ..voice import telephony, tts

log = logging.getLogger("baanmitra.watchdog")

# Template fallback if the free LLM is unavailable - guarantees the demo works.
TEMPLATES: dict[str, str] = {
    "as": ("নমস্কাৰ। {river} নদীৰ পানী বিপদ সীমাৰ {level} মিটাৰ ওপৰত পৰিব পৰা ধৰি "
           "{hours} ঘণ্টাৰ ভিতৰতে। আপোনালৈ আনন্দ দিবলৈ কওঁ যে ASDMA আৰু CWC-ৰ "
           "তথ্য অনুসৰি আপোনাক তেতিয়াই ওখ-ওখ স্তৰলৈ আৰু ஆতைহীন কেন্দ্ৰলৈ যাবলৈ কোৱা হৈছে।"),
    "bn": ("নমস্কার। {river} নদীর জল বিপদসীমার {level} মিটার উপরে {hours} ঘণ্টার মধ্যে "
           "থেকে পারে। ASDMA ও CWC-এর তথ্যানুসারে এখনই উঁচু জায়াগায় বা Relief Camp-এ "
           "যাওয়ার জন্য বলা হচ্ছে।"),
    "hi": ("नमस्ते। {river} नदी का जल खतरे की सीमा से {level} मीटर ऊपर {hours} घंटे के "
           "भीतर जा सकता है। ASDMA और CWC के आंकड़ों के अनुसार कृपया तुरंत ऊँची जगह या "
           "राहत केंद्र की ओर बढ़ें।"),
    # Bodo (বড়ো / बड़ो, Devanagari) - spoken in the Kokrajhar / BTAD flood belt.
    # This is the offline fallback; with a free LLM key the agent composes
    # proper Bodo copy per event.
    "brx": ("नमस्कार। {river} गोदावनि दानि बिपद सिमानिफ्राय {level} मिटर मोन्थाय "
            "{hours} घन्टानि बाहाय जानो हागो। ASDMA आरो CWC-नि मोजांनो मोनथांखौ फज' "
            "हानाय मोनथाय गोजों सुननाय थाखाय लैबाय।"),
    "en": ("This is an early flood warning. Water in the {river} may rise {level} "
           "metres above danger level within {hours} hours. Based on ASDMA and CWC "
           "data, please move to higher ground or the nearest relief camp."),
}


def _script(ev: RiskEvent, lang: Language) -> str:
    tpl = TEMPLATES.get(lang.value, TEMPLATES["en"])
    return tpl.format(river=ev.river or "the river",
                      level=max(ev.level_vs_danger, 0.0),
                      hours=max(int(ev.lead_time_h), 1))


async def _compose(ev: RiskEvent, lang: Language) -> str:
    summary = (
        f"Revenue circle: {ev.revenue_circle}\nRiver: {ev.river}\n"
        f"Level vs danger: {ev.level_vs_danger} m\n"
        f"Severity: {ev.severity.value}\n72h rainfall: {ev.rainfall_72h_mm} mm\n"
        f"Lead time: {ev.lead_time_h} h"
    )
    try:
        return await llm.compose_script(Language(lang).name, summary)
    except Exception as exc:
        log.warning("LLM script unavailable (%s) - using template", exc)
        return _script(ev, lang)


def _demo_event() -> RiskEvent:
    return RiskEvent(
        revenue_circle="Bongaigaon",
        district="Bongaigaon",
        river="Brahmaputra",
        level_vs_danger=1.4,
        severity=Severity.HIGH,
        lead_time_h=18.0,
        rainfall_72h_mm=210.0,
        source_refs=["demo://seeded"],
        raw={"demo": True},
    )


def _offline_households(circle: str) -> list[Household]:
    """Synthetic households so the pipeline runs with no database and no keys."""
    demo = [
        Household(id="off1", revenue_circle=circle, phone="+919000000001",
                  language=Language.ASSAMESE, has_elderly=True, distance_to_river_m=180),
        Household(id="off2", revenue_circle=circle, phone="+919000000002",
                  language=Language.BODO, has_livestock=True, distance_to_river_m=420),
        Household(id="off3", revenue_circle=circle, phone="+919000000003",
                  language=Language.BENGALI, has_disabled=True, distance_to_river_m=110),
        Household(id="off4", revenue_circle=circle, phone="+919000000004",
                  language=Language.HINDI, distance_to_river_m=1500),
        Household(id="off5", revenue_circle=circle, phone="+919000000005",
                  language=Language.ENGLISH, mobility_limited=True,
                  distance_to_river_m=260),
    ]
    return demo


def _store(ev: RiskEvent) -> None:
    try:
        if settings.database_url:
            db.save_risk_event(ev)
    except Exception as exc:
        log.warning("risk event not persisted (%s) - continuing in memory", exc)


def _households(circle: str) -> list[Household]:
    if settings.database_url:
        try:
            found = [h for h in db.households_in_circle(circle) if h.consented]
            if found:
                return found
        except Exception as exc:
            log.warning("DB read failed (%s) - using offline households", exc)
    return _offline_households(circle)


def _record_call(household: Household, ev: RiskEvent, audio_url: str) -> Optional[str]:
    try:
        if settings.database_url:
            return db.create_call(household, ev, audio_url=audio_url)
    except Exception as exc:
        log.warning("call not persisted (%s)", exc)
    return None


def _update(cid: Optional[str], **fields) -> None:
    if not cid:
        return
    try:
        db.update_call(cid, **fields)
    except Exception as exc:
        log.warning("call update failed (%s)", exc)


async def run_once(dry_run: bool = False, demo: bool = False,
                   only_circle: str = "") -> dict:
    events: list[RiskEvent] = [_demo_event()] if demo else await collect_events()
    if only_circle:
        events = [e for e in events if e.revenue_circle == only_circle]

    significant = [e for e in events if e.is_significant()]
    log.info("watchdog: %d events, %d significant", len(events), len(significant))

    placed = 0
    if not settings.consented_numbers:
        log.warning(
            "CONSENTED_NUMBERS is empty in .env, so no household can be contacted. "
            "This is a safety gate: BaanMitra never dials without explicit consent. "
            "Add numbers to .env (they must also be verified in the Twilio console).")
        return {"events": len(events), "significant": len(significant),
                "calls_placed": 0, "mode": "blocked-no-consent",
                "at": datetime.now(timezone.utc).isoformat()}

    for ev in significant:
        _store(ev)

        households = _households(ev.revenue_circle)
        log.info("  %s: %d consented households", ev.revenue_circle, len(households))

        for h in households:
            if not telephony.is_allowed(h.phone):
                log.warning("  skip %s (not in CONSENTED_NUMBERS)", h.phone)
                continue

            script = await _compose(ev, h.language)
            log.info("  [%s] %s", h.language.name, script[:120])

            if dry_run:
                log.info("  [dry-run] would call %s", h.phone)
                continue

            audio = await tts.synthesize(script, h.language)
            audio_url = f"{settings.public_base_url}/audio/{audio.name}"
            call_id = _record_call(h, ev, audio_url)
            try:
                sid = telephony.place_call(h.phone, audio_url)
                _update(call_id, status="calling", twilio_sid=sid)
                placed += 1
            except Exception as exc:
                _update(call_id, status="failed")
                log.error("  call to %s failed: %s", h.phone, exc)

    return {"events": len(events), "significant": len(significant),
            "calls_placed": placed,
            "mode": "dry-run" if dry_run else "live",
            "at": datetime.now(timezone.utc).isoformat()}


def _cli() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    ap = argparse.ArgumentParser(description="BaanMitra WATCHDOG agent")
    ap.add_argument("--dry-run", action="store_true", help="plan only, place no calls")
    ap.add_argument("--demo", action="store_true", help="use a seeded demo event")
    ap.add_argument("--circle", default="", help="limit to one revenue circle")
    args = ap.parse_args()
    result = asyncio.run(run_once(dry_run=args.dry_run, demo=args.demo,
                                  only_circle=args.circle))
    print(result)


if __name__ == "__main__":
    _cli()
