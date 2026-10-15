"""Free flood data sources: FLEWS, CWC, IMD, Open-Meteo.

Every source degrades gracefully: if a fetch or a parse fails (or the feed is
empty because it is October, not monsoon), the caller gets an empty list and a
logged warning. That is deliberate - a missing feed must never crash the agent.
"""
from . import flews, cwc, openmeteo

__all__ = ["flews", "cwc", "openmeteo", "collect_events"]

from typing import List

from ..models import RiskEvent


async def collect_events() -> List[RiskEvent]:
    events: List[RiskEvent] = []
    for mod in (flews, cwc, openmeteo):
        try:
            events.extend(await mod.fetch_events())
        except Exception as exc:  # never let one dead feed kill the run
            mod.log.warning("source %s failed: %s", mod.__name__, exc)
    return events
