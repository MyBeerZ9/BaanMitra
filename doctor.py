# -*- coding: utf-8 -*-
"""BaanMitra doctor - checks this machine against the project requirements and
prints exactly which FREE keys / database are still missing.

    python doctor.py            full check (needs internet for the network tests)
    python doctor.py --offline  skip network checks

Exit code 0 = the MACHINE is ready. Missing API keys are reported as a
checklist and never fail the run, because adding keys is a human step.
"""
from __future__ import annotations

import argparse
import importlib
import os
import platform
import shutil
import socket
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

# --------------------------------------------------------------------------- #
# requirement table - change these if the project ever grows
# --------------------------------------------------------------------------- #
MIN_PYTHON = (3, 10)
MIN_RAM_MB = 2048
MIN_DISK_MB = 1024

REQUIRED_MODULES = [
    ("fastapi", "web API + Twilio webhooks"),
    ("uvicorn", "ASGI server"),
    ("httpx", "async HTTP client (data sources, Groq)"),
    ("bs4", "FLEWS bulletin parser"),
    ("lxml", "fast HTML/XML parsing"),
    ("pydantic", "data models"),
    ("dotenv", ".env loading"),
    ("sqlalchemy", "database layer"),
    ("psycopg2", "PostgreSQL driver (Supabase)"),
    ("redis", "escalation counters (Upstash)"),
    ("twilio", "phone calls + WhatsApp"),
    ("gtts", "free fallback text-to-speech"),
    ("feedparser", "RSS/CWC feeds"),
]

# (env var, group, what stops working without it, free signup URL)
KEYS = [
    ("GROQ_API_KEY", "1 - voice + brain",
     "LLM script writing and Whisper transcription of the villager's reply",
     "https://console.groq.com/keys"),
    ("TWILIO_ACCOUNT_SID", "2 - telephony",
     "no phone call can be placed (dry-run only)", "https://twilio.com/try-twilio"),
    ("TWILIO_AUTH_TOKEN", "2 - telephony", "no phone call can be placed", ""),
    ("TWILIO_NUMBER", "2 - telephony", "no phone call can be placed", ""),
    ("CONSENTED_NUMBERS", "2 - telephony",
     "safety gate: the agent refuses to dial ANY number", "(you type it, E.164)"),
    ("DATABASE_URL", "3 - persistence",
     "calls/tickets are not saved; dashboard history stays empty",
     "https://supabase.com"),
    ("REDIS_URL", "4 - resilience",
     "escalation counters live in RAM and reset on restart (demo is fine)",
     "https://upstash.com"),
    ("BHASHINI_API_KEY", "5 - voice quality",
     "Assamese/Bodo voices fall back to gTTS, which sounds wrong",
     "https://bhashini.gov.in"),
]

CHECKS: list[tuple[str, str, str, str]] = []   # (section, level, label, detail)
_SECTION = ""


def section(name: str) -> None:
    global _SECTION
    _SECTION = name


def add(level: str, label: str, detail: str = "") -> None:
    CHECKS.append((_SECTION, level, label, detail))


def _ram_mb() -> tuple[int, int]:
    """(total_mb, free_mb) - best effort, returns (-1, -1) if unknown."""
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return (stat.ullTotalPhys // 1048576, stat.ullAvailPhys // 1048576)
        except Exception:
            return (-1, -1)
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        avail = os.sysconf("SC_AVPHYS_PAGES")
        return (page * pages // 1048576, page * avail // 1048576)
    except Exception:
        return (-1, -1)


def _tcp(host: str, port: int, timeout: float = 8.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# 1. machine
# --------------------------------------------------------------------------- #
def check_machine(offline: bool) -> None:
    section("1. MACHINE REQUIREMENTS")
    add("info", "operating system", f"{platform.platform()} ({platform.machine()})")

    ver = sys.version_info
    add("ok" if ver >= MIN_PYTHON else "fail",
        "python", f"{platform.python_version()} (need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")

    total, free = _ram_mb()
    if total < 0:
        add("info", "ram", "unknown on this platform")
    else:
        add("ok" if total >= MIN_RAM_MB else "fail", "ram",
            f"{total // 1024} GB total, {free // 1024} GB free (need >= {MIN_RAM_MB // 1024} GB)")
        if 0 <= free < 1024:
            add("warn", "ram headroom",
                "under 1 GB free - do NOT install local Indic-TTS/torch (~2 GB). "
                "Use the free Bhashini API for Assamese/Bodo voices instead.")

    free_mb = shutil.disk_usage(ROOT).free // 1048576
    add("ok" if free_mb >= MIN_DISK_MB else "fail", "disk",
        f"{free_mb // 1024} GB free (need >= {MIN_DISK_MB // 1024} GB)")

    add("ok" if shutil.which("git") else "warn", "git",
        "found" if shutil.which("git") else "not found (only needed to clone/push)")

    if not offline:
        for host, why in (("pypi.org", "installing dependencies"),
                          ("api.open-meteo.com", "live rainfall data"),
                          ("api.github.com", "cron + repo")):
            add("ok" if _tcp(host, 443) else "warn", f"internet: {host}", why)


# --------------------------------------------------------------------------- #
# 2. dependencies
# --------------------------------------------------------------------------- #
def check_dependencies() -> None:
    section("2. PROJECT DEPENDENCIES")
    missing = []
    for mod, why in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(mod)
    if missing:
        add("fail", "python packages",
            "missing " + ", ".join(missing)
            + "  ->  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    else:
        add("ok", "python packages", f"all {len(REQUIRED_MODULES)} required imports OK")

    try:
        importlib.import_module("baanmitra.config")
        add("ok", "baanmitra package", "importable (pip install -e .)")
    except Exception as exc:
        add("fail", "baanmitra package",
            f"{exc}  ->  .\\.venv\\Scripts\\python.exe -m pip install -e .")

    for path, why in (("src/baanmitra/api/main.py", "API"),
                      ("data/revenue_circles.csv", "seed data"),
                      ("data/fixtures/flews_sample.html", "offline FLEWS fixture"),
                      ("data/fixtures/cwc_levels.json", "offline CWC fixture"),
                      ("dashboard/index.html", "dashboard")):
        full = os.path.join(ROOT, path.replace("/", os.sep))
        add("ok" if os.path.exists(full) else "fail", "file: " + path, why)


# --------------------------------------------------------------------------- #
# 3. .env + keys
# --------------------------------------------------------------------------- #
def _read_env() -> dict[str, str]:
    """OS environment first, then .env (which wins if both define a key)."""
    values = {k: v for k, v in os.environ.items()}
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def check_keys() -> None:
    section("3. FREE KEYS / DATABASE")
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        add("warn", ".env file",
            "not found - copy .env.example to .env (setup.ps1 does this for you)")
    else:
        add("ok", ".env file", "found")

    env = _read_env()
    groups: dict[str, list[bool]] = {}
    for var, group, breaks, url in KEYS:
        val = env.get(var, "").strip()
        groups.setdefault(group, []).append(bool(val))
        if val:
            add("ok", var, f"set ({len(val)} chars, value hidden)")
        else:
            add("missing", var, f"MISSING - {breaks}" + (f"   sign up: {url}" if url else ""))

    ready = sum(1 for flags in groups.values() if all(flags))
    add("info", "key groups configured", f"{ready} of {len(groups)}")

    # --- config warnings that break a live run -------------------------------
    if env.get("CRON_TOKEN", "change-me") == "change-me":
        add("warn", "CRON_TOKEN",
            "still 'change-me' - anyone could trigger an alert cycle. Set a random string.")

    base = env.get("PUBLIC_BASE_URL", "http://localhost:8000")
    if "localhost" in base or "127.0.0.1" in base:
        add("warn", "PUBLIC_BASE_URL",
            "points at localhost - Twilio cannot reach your audio, so the call "
            "connects but plays silence. Use a tunnel (ngrok http 8000) or the "
            "Render URL.")
    else:
        add("ok", "PUBLIC_BASE_URL", base)

    db_url = env.get("DATABASE_URL", "").strip()
    if not db_url:
        add("info", "DATABASE_URL advice",
            "Supabase free project -> Connect button -> SESSION POOLER string, "
            "percent-encode the password, append ?sslmode=require")
    else:
        if db_url.startswith("postgres://"):
            add("ok", "DATABASE_URL scheme", "postgres:// is auto-upgraded to postgresql://")
        host = db_url.split("@")[1].split("/")[0].split(":")[0] if "@" in db_url else ""
        if host.startswith("db."):
            add("warn", "DATABASE_URL host",
                "direct connection (db.xxx.supabase.co) is IPv6-only on the free "
                "plan - it times out from IPv4 networks. Use the SESSION POOLER "
                "host instead (aws-0-xxx.pooler.supabase.com).")
        elif "pooler.supabase.com" in host:
            add("ok", "DATABASE_URL host", "session pooler (IPv4) - correct choice")
        if ":6543" in db_url:
            add("warn", "DATABASE_URL port",
                "6543 = transaction pooler, which does not support prepared "
                "statements. Use the session pooler string (port 5432).")
        if "sslmode=" not in db_url:
            add("warn", "DATABASE_URL ssl",
                "append ?sslmode=require so the connection is always encrypted")


# --------------------------------------------------------------------------- #
# 4. local runtime
# --------------------------------------------------------------------------- #
def check_runtime() -> None:
    section("4. LOCAL RUNTIME")
    for port in (8000,):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            busy = s.connect_ex(("127.0.0.1", port)) == 0
        add("warn" if busy else "ok", f"port {port}",
            "already in use - another instance is running"
            if busy else "free for the API + dashboard")

    venv = os.path.join(ROOT, ".venv", "Scripts" if sys.platform == "win32" else "bin")
    add("ok" if os.path.isdir(venv) else "warn", "virtualenv",
        ".venv found" if os.path.isdir(venv) else "not created yet - run .\\setup.ps1")


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="BaanMitra system + configuration doctor")
    ap.add_argument("--offline", action="store_true", help="skip network checks")
    args = ap.parse_args()

    print("=" * 78)
    print("BAANMITRA DOCTOR - system requirements proof + what you must fix")
    print("=" * 78)

    check_machine(args.offline)
    check_dependencies()
    check_keys()
    check_runtime()

    width = max(len(lbl) for _, _, lbl, _ in CHECKS)
    fails = 0
    missing = 0
    current = ""
    for sec, level, label, detail in CHECKS:
        if sec != current:
            print(f"\n--- {sec} " + "-" * (78 - len(sec) - 4))
            current = sec

        mark = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]",
                "missing": "[....]", "info": "[info]"}[level]
        print(f"{mark} {label.ljust(width)}  {detail}")
        fails += 1 if level == "fail" else 0
        missing += 1 if level == "missing" else 0

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    if fails:
        print(f"  MACHINE NOT READY - {fails} failed check(s) above. Fix those first.")
        return 1
    print("  MACHINE READY - this computer meets every requirement to run BaanMitra.")
    if missing:
        print(f"  Still missing {missing} free key(s)/setting(s) (marked [....] above).")
        print("  The code still runs without them, in degraded mode:")
        print("    no keys   -> offline demo: templates + gTTS, no calls, no history")
        print("    all keys  -> live alert cycle: real calls, real transcripts")
        print("  Order to add them: Groq -> Twilio -> Supabase -> Upstash -> Bhashini")
        print("  Step-by-step: docs/SETUP.md")
    else:
        print("  CONFIGURED - every free key is in place. Run the full cycle:")
        print("      .\\.venv\\Scripts\\python.exe -m baanmitra.agents.watchdog --dry-run")
        print("      .\\.venv\\Scripts\\python.exe -m baanmitra.api.main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
