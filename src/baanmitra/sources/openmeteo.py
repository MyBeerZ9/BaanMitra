"""Open-Meteo rainfall forecasts - FREE, NO API KEY AT ALL.

https://open-meteo.com/  ·  https://api.open-meteo.com/v1/forecast
This is the always-available cross-check source: it needs no key, no card and no
registration, so BaanMitra never comes back completely empty.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import httpx

from ..models import Language, RiskEvent, Severity

log = logging.getLogger("baanmitra.openmeteo")

API = "https://api.open-meteo.com/v1/forecast"

# Representative points for the 12 seeded revenue circles.
CIRCLE_POINTS: Dict[str, tuple[float, float, str]] = {
    "Bongaigaon": (26.4769, 90.5640, "Bongaigaon"),
    "Sidli": (26.4833, 90.0667, "Kokrajhar"),
    "Goalpara": (26.1700, 90.6200, "Goalpara"),
    "Barpeta": (26.3200, 91.0000, "Barpeta"),
    "Nalbari": (26.4400, 91.4400, "Nalbari"),
    "Lakhimpur": (27.2300, 94.1100, "Lakhimpur"),
    "Dhemaji": (27.4800, 94.5800, "Dhemaji"),
    "Morigaon": (26.2500, 92.3400, "Morigaon"),
    "Dhubri": (26.0200, 89.9800, "Dhubri"),
    "Sonitpur": (26.6300, 92.8000, "Sonitpur"),
    "Sivasagar": (26.9800, 94.6300, "Sivasagar"),
    "Silchar": (24.8300, 92.7800, "Cachar"),
}


def _severity_from_rain(mm72: float) -> Severity:
    if mm72 >= 300:
        return Severity.VERY_HIGH
    if mm72 >= 200:
        return Severity.HIGH
    if mm72 >= 120:
        return Severity.MODERATE
    return Severity.LOW


async def fetch_events(circles: List[str] | None = None) -> List[RiskEvent]:
    names = circles or list(CIRCLE_POINTS)
    now = datetime.now(timezone.utc)
    out: List[RiskEvent] = []

    async with httpx.AsyncClient(timeout=25) as client:
        for name in names:
            point = CIRCLE_POINTS.get(name)
            if not point:
                continue
            lat, lon, district = point
            try:
                r = await client.get(API, params={
                    "latitude": lat, "longitude": lon,
                    "daily": "precipitation_sum",
                    "forecast_days": 4,
                    "timezone": "Asia/Kolkata",
                })
                r.raise_for_status()
                daily = r.json().get("daily", {})
            except Exception as exc:
                log.warning("Open-Meteo failed for %s: %s", name, exc)
                continue

            rains = [v or 0.0 for v in daily.get("precipitation_sum", [])][:3]
            mm72 = round(sum(rains), 1)
            out.append(RiskEvent(
                revenue_circle=name,
                district=district,
                river="Brahmaputra basin" if lon < 92.5 else "Barak basin",
                level_vs_danger=0.0,
                severity=_severity_from_rain(mm72),
                valid_from=now,
                valid_to=now + timedelta(hours=72),
                lead_time_h=72.0,
                rainfall_72h_mm=mm72,
                source_refs=[API],
                raw={"precipitation_daily_mm": rains},
            ))
    log.info("Open-Meteo: %d circle forecasts fetched", len(out))
    return out


def language_for(district: str) -> Language:
    """Sensible default alert language per district (Bodo in BTAD areas)."""
    bodo_areas = {"Kokrajhar", "Udalguri", "Baksa", "Chirang"}
    barak = {"Cachar", "Hailakandi", "Karimganj"}
    if district in bodo_areas:
        return Language.BODO
    if district in barak:
        return Language.BENGALI
    return Language.ASSAMESE
