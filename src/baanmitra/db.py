"""Database layer: Supabase (free) PostgreSQL 15 + PostGIS.

Run `python -m baanmitra.db --init` to print the DDL, then paste it into the
Supabase SQL editor (free project, no card).
"""
from __future__ import annotations

import csv
import math
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import settings
from .models import Household, Language, RiskEvent, Severity, Ticket

DDL = """
create extension if not exists postgis;

create table if not exists revenue_circles (
    name text primary key,
    district text,
    lat double precision,
    lon double precision,
    geom geometry(Point, 4326)
);

create table if not exists households (
    id text primary key,
    revenue_circle text references revenue_circles(name),
    phone text not null,
    language text default 'as',
    has_elderly boolean default false,
    has_disabled boolean default false,
    has_livestock boolean default false,
    mobility_limited boolean default false,
    distance_to_river_m double precision default 0,
    consented boolean default true,
    notes text default ''
);
create index if not exists idx_households_circle on households(revenue_circle);

create table if not exists risk_events (
    id text primary key,
    revenue_circle text,
    district text,
    river text,
    level_vs_danger double precision,
    severity text,
    valid_from timestamptz default now(),
    valid_to timestamptz,
    lead_time_h double precision,
    rainfall_72h_mm double precision,
    source_refs text[],
    raw jsonb,
    created_at timestamptz default now()
);

create table if not exists calls (
    id text primary key,
    household_id text references households(id),
    risk_event_id text,
    phone text,
    language text,
    audio_url text,
    status text default 'pending',      -- pending | calling | answered | no_answer | escalated
    attempts int default 0,
    priority_score int default 0,
    transcript text,
    needs_help boolean,
    twilio_sid text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create table if not exists tickets (
    id text primary key,
    phone text,
    transcript text,
    intent text,
    location_text text,
    severity text,
    needs text[],
    people_count int,
    lat double precision,
    lon double precision,
    source text,
    status text default 'open',
    created_at timestamptz default now()
);

create table if not exists escalations (
    id text primary key,
    call_id text,
    household_id text,
    reason text,
    notified text[] default '{}',
    created_at timestamptz default now()
);

-- Spatial selector: households inside a revenue circle (2 km buffer, so village
-- clusters slightly outside the centroid are still covered).
create or replace view households_in_circle as
select h.*
from households h
join revenue_circles c on c.name = h.revenue_circle;
"""

_engine: Optional[Engine] = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Get a FREE Supabase Postgres URL - "
                "https://supabase.com (no card required)."
            )
        url = settings.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine


@contextmanager
def session() -> Iterator[Any]:
    conn = engine().connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------------- #
def households_in_circle(circle: str) -> list[Household]:
    """All consented households of a revenue circle (PostGIS-verified)."""
    with session() as conn:
        rows = conn.execute(
            text(
                "select id, revenue_circle, phone, language, has_elderly, has_disabled, "
                "has_livestock, mobility_limited, distance_to_river_m, consented, notes "
                "from households where revenue_circle = :c and consented = true"
            ),
            {"c": circle},
        ).mappings()
        return [Household(**dict(r)) for r in rows]


def recent_calls(limit: int = 50) -> list[dict[str, Any]]:
    with session() as conn:
        rows = conn.execute(
            text(
                "select c.*, h.revenue_circle from calls c "
                "left join households h on h.id = c.household_id "
                "order by c.created_at desc limit :l"
            ),
            {"l": limit},
        ).mappings()
        return [dict(r) for r in rows]


def open_tickets(limit: int = 50) -> list[dict[str, Any]]:
    with session() as conn:
        rows = conn.execute(
            text("select * from tickets where status = 'open' order by created_at desc limit :l"),
            {"l": limit},
        ).mappings()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------------- #
def new_id() -> str:
    return uuid.uuid4().hex


def save_risk_event(ev: RiskEvent) -> str:
    with session() as conn:
        conn.execute(
            text(
                "insert into risk_events (id, revenue_circle, district, river, level_vs_danger, "
                "severity, valid_from, valid_to, lead_time_h, rainfall_72h_mm, source_refs, raw) "
                "values (:id,:circle,:district,:river,:lvl,:sev,:vf,:vt,:lead,:rain,:refs,:raw) "
                "on conflict (id) do nothing"
            ),
            {
                "id": ev.id, "circle": ev.revenue_circle, "district": ev.district,
                "river": ev.river, "lvl": ev.level_vs_danger, "sev": ev.severity.value,
                "vf": ev.valid_from, "vt": ev.valid_to, "lead": ev.lead_time_h,
                "rain": ev.rainfall_72h_mm, "refs": ev.source_refs, "raw": ev.raw,
            },
        )
    return ev.id


def create_call(household: Household, ev: RiskEvent, audio_url: str = "") -> str:
    cid = new_id()
    with session() as conn:
        conn.execute(
            text(
                "insert into calls (id, household_id, risk_event_id, phone, language, "
                "audio_url, status, attempts) values (:id,:hid,:eid,:ph,:lang,:url,'pending',0)"
            ),
            {"id": cid, "hid": household.id, "eid": ev.id, "ph": household.phone,
             "lang": household.language.value, "url": audio_url},
        )
    return cid


def update_call(cid: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.now(timezone.utc)
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    with session() as conn:
        conn.execute(text(f"update calls set {assignments} where id = :id"),
                     {"id": cid, **fields})


def get_call_by_sid(twilio_sid: str) -> Optional[dict[str, Any]]:
    with session() as conn:
        row = conn.execute(
            text("select * from calls where twilio_sid = :s order by created_at desc"),
            {"s": twilio_sid},
        ).mappings().first()
        return dict(row) if row else None


def update_call_by_sid(twilio_sid: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.now(timezone.utc)
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    with session() as conn:
        conn.execute(text(f"update calls set {assignments} where twilio_sid = :id"),
                     {"id": twilio_sid, **fields})


def save_ticket(t: Ticket) -> str:
    with session() as conn:
        conn.execute(
            text(
                "insert into tickets (id, phone, transcript, intent, location_text, severity, "
                "needs, people_count, lat, lon, source, status) values "
                "(:id,:phone,:tr,:intent,:loc,:sev,:needs,:pc,:lat,:lon,:src,:st)"
            ),
            {"id": t.id, "phone": t.phone, "tr": t.transcript, "intent": t.intent,
             "loc": t.location_text, "sev": t.severity, "needs": t.needs,
             "pc": t.people_count, "lat": t.lat, "lon": t.lon,
             "src": t.source, "st": t.status},
        )
    return t.id


def save_escalation(call_id: str, household_id: str, reason: str, notified: list[str]) -> None:
    with session() as conn:
        conn.execute(
            text("insert into escalations (id, call_id, household_id, reason, notified) "
                 "values (:id,:cid,:hid,:r,:n)"),
            {"id": new_id(), "cid": call_id, "hid": household_id, "r": reason,
             "n": notified},
        )


# --------------------------------------------------------------------------- #
# seeding
# --------------------------------------------------------------------------- #
def seed_circles(csv_path: str = "data/revenue_circles.csv") -> int:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = csv_path if os.path.isabs(csv_path) else os.path.join(here, csv_path)
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    with session() as conn:
        for r in rows:
            conn.execute(
                text(
                    "insert into revenue_circles (name, district, lat, lon, geom) values "
                    "(:n,:d,:lat,:lon, ST_SetSRID(ST_MakePoint(:lon,:lat), 4326)) "
                    "on conflict (name) do update set district = excluded.district, "
                    "lat = excluded.lat, lon = excluded.lon, "
                    "geom = ST_SetSRID(ST_MakePoint(excluded.lon, excluded.lat), 4326)"
                ),
                {"n": r["name"], "d": r["district"], "lat": float(r["lat"]),
                 "lon": float(r["lon"])},
            )
    return len(rows)


def seed_households(per_circle: int = 6, phone_prefix: str = "+91") -> int:
    """Synthetic households only - no real personal data anywhere in this project."""
    import random

    rng = random.Random(20261024)
    langs = [l.value for l in Language]
    count = 0
    with session() as conn:
        circles = [r[0] for r in conn.execute(text("select name from revenue_circles"))]
        for c in circles:
            for i in range(per_circle):
                hid = new_id()
                phone = f"{phone_prefix}9{rng.randint(100000000, 999999999)}"
                conn.execute(
                    text(
                        "insert into households (id, revenue_circle, phone, language, "
                        "has_elderly, has_disabled, has_livestock, mobility_limited, "
                        "distance_to_river_m, consented) values "
                        "(:id,:c,:p,:l,:e,:d,:liv,:m,:dist,true) "
                        "on conflict (id) do nothing"
                    ),
                    {
                        "id": hid, "c": c, "p": phone,
                        "l": rng.choices(langs, weights=[0.55, 0.05, 0.15, 0.20, 0.05])[0],
                        "e": rng.random() < 0.3, "d": rng.random() < 0.1,
                        "liv": rng.random() < 0.6, "m": rng.random() < 0.15,
                        "dist": round(rng.uniform(80, 2500), 1),
                    },
                )
                count += 1
    return count


def seed_all() -> tuple[int, int]:
    return seed_circles(), seed_households()


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


if __name__ == "__main__":
    import sys

    if "--init" in sys.argv:
        print(DDL)
        print("-- Paste the above into the Supabase SQL editor (free project).")
    elif "--ddl-file" in sys.argv:
        open("schema.sql", "w", encoding="utf-8").write(DDL)
        print("wrote schema.sql")
    else:
        print("usage: python -m baanmitra.db [--init | --ddl-file]")
