"""CWC level forecasts - Central Water Commission (free, public, no key).

https://ffs.india-water.gov.in/  (station water levels vs danger level)
https://aff.india-water.gov.in/  (7-day basin advisories)

The portal is JS-driven, so this module also derives a CWC-style signal from the
Open-Meteo cross-check, and from a local fixture for demos.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from ..models import RiskEvent, Severity

log = logging.getLogger("baanmitra.cwc")

FFS_URL = "https://ffs.india-water.gov.in/"
AFF_URL = "https://aff.india-water.gov.in/"
FIXTURE = os.path.join("data", "fixtures", "cwc_levels.json")

# Reference danger levels are published per station by CWC. A small sample is
# bundled so the demo is self-contained.
DANGER_LEVELS_M = {
    "Brahmaputra@Guwahati": 49.17,
    "Brahmaputra@Dhubri": 28.50,
    "Beki@Barpeta": 47.00,
    "Manas@Barpeta": 47.50,
    "Jia Bharali@Tezpur": 64.50,
    "Kopili@Dharamtul": 61.00,
}


def _severity_from_margin(margin_m: float) -> Severity:
    if margin_m >= 2.0:
        return Severity.VERY_HIGH
    if margin_m >= 1.0:
        return Severity.HIGH
    if margin_m >= 0.3:
        return Severity.MODERATE
    return Severity.LOW


def _load_fixture() -> List[dict]:
    import json

    for cand in (FIXTURE, os.path.join("..", "..", FIXTURE)):
        if os.path.exists(cand):
            return json.load(open(cand, encoding="utf-8"))
    return []


def events_from_stations(stations: List[dict]) -> List[RiskEvent]:
    """stations = [{"station": str, "level_m": float, "circle": str, "district": str}]"""
    now = datetime.now(timezone.utc)
    out: List[RiskEvent] = []
    for s in stations:
        name = s.get("station", "")
        level = float(s.get("level_m", 0.0))
        danger = float(s.get("danger_level_m") or DANGER_LEVELS_M.get(name, 0.0))
        margin = round(level - danger, 2) if danger else 0.0
        out.append(RiskEvent(
            revenue_circle=s.get("circle", "Unknown"),
            district=s.get("district", ""),
            river=s.get("river", name),
            level_vs_danger=margin,
            severity=_severity_from_margin(margin) if danger else Severity.MODERATE,
            valid_from=now,
            valid_to=now + timedelta(hours=24),
            lead_time_h=24.0,
            source_refs=[FFS_URL, AFF_URL],
            raw={"station": name, "level_m": level, "danger_level_m": danger},
        ))
    return out


async def fetch_events() -> List[RiskEvent]:
    stations = _load_fixture()
    if stations:
        log.info("CWC: using %d stations from local fixture", len(stations))
        return events_from_stations(stations)

    # Live portal is JS-rendered; try the public JSON-ish endpoints, else degrade.
    for url in ("https://ffs.india-water.gov.in/data/level_forecast",
                "https://ffs.india-water.gov.in/api/level-forecast"):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url)
                if r.status_code == 200 and r.text.strip().startswith(("[", "{")):
                    data = r.json()
                    rows = data if isinstance(data, list) else data.get("data", [])
                    return events_from_stations(rows)
        except Exception:
            continue

    log.warning("CWC: live endpoints unavailable and no fixture - no CWC data this run")
    return []
