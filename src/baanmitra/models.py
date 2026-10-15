"""Domain models: RiskEvent, Household, Ticket."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    FLOOD_WATCH = "flood_watch"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"

    @property
    def weight(self) -> int:
        return {
            "flood_watch": 0,
            "low": 1,
            "moderate": 2,
            "high": 3,
            "very_high": 4,
        }[self.value]


class Language(str, Enum):
    ASSAMESE = "as"
    BODO = "brx"
    BENGALI = "bn"
    HINDI = "hi"
    ENGLISH = "en"


LANG_NAME = {
    Language.ASSAMESE: "Assamese",
    Language.BODO: "Bodo",
    Language.BENGALI: "Bengali",
    Language.HINDI: "Hindi",
    Language.ENGLISH: "English",
}


class RiskEvent(BaseModel):
    """One normalised flood risk event, produced from any official source."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    revenue_circle: str
    district: str = ""
    river: str = ""
    level_vs_danger: float = 0.0          # metres above danger level
    severity: Severity = Severity.MODERATE
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: Optional[datetime] = None
    lead_time_h: float = 24.0
    rainfall_72h_mm: float = 0.0
    source_refs: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    def is_significant(self) -> bool:
        """Threshold rule. The LLM may override this in agents.watchdog."""
        return self.severity.weight >= Severity.MODERATE.weight or (
            self.level_vs_danger >= 0.5 or self.rainfall_72h_mm >= 150.0
        )


class Household(BaseModel):
    id: str
    revenue_circle: str
    phone: str                      # E.164, verified + consented
    language: Language = Language.ASSAMESE
    has_elderly: bool = False
    has_disabled: bool = False
    has_livestock: bool = False
    mobility_limited: bool = False
    distance_to_river_m: float = 0.0
    consented: bool = True
    notes: str = ""

    def priority_score(self) -> int:
        score = 0
        score += 3 if self.has_elderly else 0
        score += 3 if self.has_disabled else 0
        score += 2 if self.mobility_limited else 0
        score += 1 if self.has_livestock else 0
        score += 2 if self.distance_to_river_m < 500 else 0
        return score


class Ticket(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    phone: str
    transcript: str = ""
    intent: str = "other"            # rescue | shelter | food | medical | info | other
    location_text: str = ""
    severity: str = "medium"         # low | medium | high | critical
    needs: list[str] = Field(default_factory=list)
    people_count: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    source: str = "whatsapp"
    status: str = "open"             # open | assigned | resolved
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
