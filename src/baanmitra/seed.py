"""Seed the free Supabase database: revenue circles + synthetic households.

    python -m baanmitra.seed

Only synthetic data is created. No real personal information is ever stored.
"""
from __future__ import annotations

import logging

from . import db

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


def main() -> None:
    circles = db.seed_circles()
    households = db.seed_households(per_circle=6)
    print(f"seeded {circles} revenue circles and {households} synthetic households")
    print("next: python -m baanmitra.agents.watchdog --dry-run")


if __name__ == "__main__":
    main()
