"""FLEWS bulletins - ASDMA / NESAC (free, public, no key).

https://asdma.gov.in/project_flood_warning.html
Real bulletins are only published during the monsoon (roughly Jun-Oct). The
parser therefore supports a local fixture so the demo works all year:
  data/fixtures/flews_sample.html
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

import httpx
from bs4 import BeautifulSoup

from ..models import RiskEvent, Severity

log = logging.getLogger("baanmitra.flews")

URL = "https://asdma.assam.gov.in/resource/flood-alerts"
FIXTURE = os.path.join("data", "fixtures", "flews_sample.html")

_SEV_WORDS = {
    "very high": Severity.VERY_HIGH, "high": Severity.HIGH,
    "moderate": Severity.MODERATE, "low": Severity.LOW,
    "watch": Severity.FLOOD_WATCH,
}


def _severity(text: str) -> Severity:
    t = text.lower()
    for k in ("very high", "high", "moderate", "low", "watch"):
        if k in t:
            return _SEV_WORDS[k]
    return Severity.MODERATE


def _fixture_exists() -> bool:
    for cand in (FIXTURE, os.path.join("..", "..", FIXTURE)):
        if os.path.exists(cand):
            return cand
    return ""


def parse_html(html: str, limit: int = 12) -> List[RiskEvent]:
    soup = BeautifulSoup(html, "lxml")
    events: List[RiskEvent] = []
    now = datetime.now(timezone.utc)

    for row in soup.select("table tr")[1:limit + 1]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        joined = " ".join(cells)
        events.append(RiskEvent(
            revenue_circle=cells[0] or "Unknown",
            district=cells[1] if len(cells) > 1 else "",
            severity=_severity(joined),
            valid_from=now,
            valid_to=now + timedelta(hours=24),
            lead_time_h=24.0,
            source_refs=[URL],
            raw={"cells": cells},
        ))
    return events


async def fetch_events(use_fixture: bool = True) -> List[RiskEvent]:
    fixture = _fixture_exists() if use_fixture else ""
    html = ""

    if fixture:
        log.info("FLEWS: parsing local fixture %s", fixture)
        html = open(fixture, encoding="utf-8").read()
    else:
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.get(URL)
                r.raise_for_status()
                html = r.text
        except Exception as exc:
            log.warning("FLEWS fetch failed (%s) - using no data", exc)
            return []

    events = parse_html(html)
    if not events:
        log.info("FLEWS: no bulletins parsed (feed may be empty outside monsoon)")
    return events
