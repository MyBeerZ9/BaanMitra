# -*- coding: utf-8 -*-
"""BaanMitra smoke test - runs fully offline, no API keys, no database.

    python smoke_test.py            # from the project root
    python smoke_test.py --quick    # skip the FastAPI TestClient part

Exits non-zero if any check fails.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import warnings

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

# Keep test output readable; set SMOKE_VERBOSE=1 to see every log line.
if not os.environ.get("SMOKE_VERBOSE"):
    logging.basicConfig(level=logging.CRITICAL)
    logging.getLogger("baanmitra").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn, optional: bool = False):
    try:
        detail = fn()
        RESULTS.append((name, True, detail or "ok"))
    except Exception as exc:
        if optional:
            RESULTS.append((name, None, f"SKIPPED - {type(exc).__name__}: {exc}"))
        else:
            RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


# --------------------------------------------------------------------------- #
def t_models() -> str:
    from baanmitra.models import Household, Language, RiskEvent, Severity
    h = Household(id="x", revenue_circle="B", phone="+919999999999",
                  language=Language.ASSAMESE, has_elderly=True,
                  distance_to_river_m=200)
    assert h.priority_score() == 5, h.priority_score()
    ev = RiskEvent(revenue_circle="B", severity=Severity.HIGH, level_vs_danger=1.2)
    assert ev.is_significant()
    ev2 = RiskEvent(revenue_circle="B", severity=Severity.LOW, level_vs_danger=0.1)
    assert not ev2.is_significant()
    return "priority=5, threshold logic OK"


def t_config() -> str:
    from baanmitra.config import settings
    assert settings.escalation_attempts >= 1
    return f"escalation_attempts={settings.escalation_attempts}"


def t_sources_offline() -> str:
    import asyncio
    from baanmitra.sources import cwc, flews
    f = asyncio.run(flews.fetch_events())
    c = asyncio.run(cwc.fetch_events())
    assert f, "FLEWS fixture produced no events"
    assert c, "CWC fixture produced no events"
    return f"FLEWS={len(f)} fixtures, CWC={len(c)} stations"


def t_scripts() -> str:
    from baanmitra.agents.watchdog import TEMPLATES
    from baanmitra.models import Language, RiskEvent, Severity
    ev = RiskEvent(revenue_circle="Bongaigaon", river="Brahmaputra",
                   level_vs_danger=1.4, severity=Severity.HIGH, lead_time_h=18)
    missing = [lang.value for lang in Language if lang.value not in TEMPLATES]
    assert not missing, f"no offline template for: {missing}"
    out = []
    for lang in Language:
        txt = TEMPLATES[lang.value].format(river=ev.river, level=1.4, hours=18)
        assert "18" in txt, (lang, txt)
        out.append(f"{lang.name}:{len(txt)}ch")
    return ", ".join(out)


def t_offline_households() -> str:
    from baanmitra.agents.watchdog import _offline_households
    hs = _offline_households("Bongaigaon")
    assert len(hs) == 5
    langs = {h.language.value for h in hs}
    assert langs == {"as", "brx", "bn", "hi", "en"}, langs
    return f"5 synthetic households, languages={sorted(langs)}"


def t_watchdog_blocked() -> str:
    """With an empty allowlist the agent must refuse to dial anything."""
    from baanmitra.agents import watchdog
    r = asyncio.run(watchdog.run_once(demo=True))
    assert r["calls_placed"] == 0, r
    assert r["mode"] == "blocked-no-consent", r
    return f"mode={r['mode']}, significant={r['significant']}"


def t_watchdog_dryrun() -> str:
    """With a consent allowlist, dry-run must compose every script and place no call."""
    os.environ["CONSENTED_NUMBERS"] = "+919000000001,+919000000002"
    from baanmitra import config
    config.settings.consented_numbers = {"+919000000001", "+919000000002"}
    from baanmitra.agents import watchdog
    r = asyncio.run(watchdog.run_once(demo=True, dry_run=True))
    assert r["mode"] == "dry-run", r
    assert r["calls_placed"] == 0, r
    return f"dry-run planned for {r['significant']} event(s)"


def t_tts() -> str:
    """Free TTS chain must produce a real audio file (gTTS fallback needs no key)."""
    from baanmitra.models import Language
    from baanmitra.voice import tts
    p = asyncio.run(tts.synthesize("Flood warning test. Move to higher ground.",
                                   Language.ENGLISH))
    size = p.stat().st_size
    assert size > 1000, f"audio too small: {size} bytes"
    return f"gTTS fallback -> {p.name} ({size} bytes)"


def t_api() -> str:
    from fastapi.testclient import TestClient
    from baanmitra.api import main
    with TestClient(main.app) as client:
        h = client.get("/healthz")
        assert h.status_code == 200 and h.json()["cost"] == "Rs 0", h.text
        d = client.get("/dashboard/data")
        assert d.status_code == 200, d.text
        assert "stats" in d.json()
        page = client.get("/dashboard/")
        assert page.status_code == 200 and "BaanMitra" in page.text
    return "healthz, /dashboard/data, /dashboard/ all 200"


def main() -> int:
    check("models / priority scoring", t_models)
    check("config", t_config)
    check("sources (offline fixtures)", t_sources_offline)
    check("multilingual alert scripts", t_scripts)
    check("offline households", t_offline_households)
    check("watchdog consent gate", t_watchdog_blocked)
    check("watchdog dry-run", t_watchdog_dryrun)
    check("free TTS chain", t_tts, optional=True)   # needs internet for gTTS
    if "--quick" not in sys.argv:
        check("FastAPI endpoints", t_api)

    width = max(len(n) for n, _, _ in RESULTS)
    failed = 0
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
        print(f"  [{mark}] {name.ljust(width)}  {detail}")
        failed += 0 if ok else 1

    print()
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} checks passed"
          + ("" if not failed else f"  ({failed} FAILED)"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
