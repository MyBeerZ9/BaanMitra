# BaanMitra (বানমিত্ৰা)

**The last mile of India's flood early warning system.**

Every existing system forecasts the flood. None of them talks to the villager.

BaanMitra turns official flood forecasts (FLEWS / CWC / IMD) into **outbound voice calls in
Assamese, Bodo, Bengali or Hindi** to at-risk households, asks two safety questions, records a
**priority score**, **retries and escalates** unanswered calls up the gaon-bura → DDMA chain,
and turns **inbound WhatsApp voice notes** after the flood into structured, geotagged relief
tickets.

Built for **Hackyard Build 2026**, IIT Guwahati, 24–25 October 2026.

---

## ⚠️ THE MONEY RULE: this build is 100% free

**No credit card is required anywhere in this project.** Every service below has a genuine
free tier; see [COSTS.md](COSTS.md) for the exact limits and for the two hackathon sponsor
tracks (Agent37, Nodus) that are *deliberately excluded* because they need paid credits.

| Need | Free service used | Card needed? |
|---|---|---|
| LLM reasoning | **Groq** (`openai/gpt-oss-120b`) | ❌ no |
| Speech-to-text | **Groq** `whisper-large-v3` | ❌ no |
| Text-to-speech (Assamese/Bodo/Bengali/Hindi) | **Bhashini API** → **AI4Bharat Indic-TTS** (local, MIT/Apache) → **ttsfree.in** → gTTS | ❌ no |
| Phone calls + WhatsApp | **Twilio trial** | ❌ no |
| Database (PostgreSQL + PostGIS) | **Supabase** free project | ❌ no |
| Queue / rate limits | **Upstash Redis** free | ❌ no |
| Hosting | **Render** free web service | ❌ no |
| Scheduled ingest | **GitHub Actions** cron | ❌ no |
| Maps | **MapLibre GL + OpenStreetMap / CARTO** | ❌ no |

---

## Quick start (5 commands)

```powershell
# 1. create the virtualenv and install every dependency (all free/open-source)
.\setup.ps1

# 2. prove this machine meets the requirements, and see which keys are still missing
.\.venv\Scripts\python.exe doctor.py

# 3. add your free-tier keys
notepad .env

# 4. seed the database (12 revenue circles + synthetic households, no real PII)
.\.venv\Scripts\python.exe -m baanmitra.seed

# 5. run the API + dashboard locally
.\.venv\Scripts\python.exe -m baanmitra.api.main

# 6. open the dashboard
start http://localhost:8000/dashboard/
```

**No keys yet? That is fine** — the pipeline already runs offline (live data
collection, 5-language alert templates, gTTS audio, the consent gate). Adding
keys upgrades it to real phone calls and real transcripts; see
[docs/SETUP.md](docs/SETUP.md) for exactly what to fix and in what order.

Then trigger one full flood-alert cycle end to end:

```powershell
.\.venv\Scripts\python.exe -m baanmitra.agents.watchdog
```

---

## Getting the free keys (10 minutes total)

1. **Groq** — https://console.groq.com/keys — email only, no card. Gives you the LLM *and*
   Whisper STT in one key.
2. **Supabase** — https://supabase.com — new **Free** project, no card. In the
   **SQL Editor** run the DDL printed by `python -m baanmitra.db --init` (its first
   line enables **PostGIS**, which Supabase pre-installs on every plan). Then click
   **Connect → Session pooler** and copy that string — *not* the direct one, which is
   IPv6-only on the free plan. Gotchas and the exact string format: [docs/SETUP.md](docs/SETUP.md).
3. **Upstash** — https://upstash.com — free Redis, copy the `rediss://` URL.
4. **Bhashini** — https://bhashini.gov.in — register, create an API key. Optional but this is
   what gives you real **Assamese and Bodo** voices with zero local compute.
   *(Optional: ttsfree.in free account → API key, built on AI4Bharat Indic Parler-TTS.)*
5. **Twilio** — https://twilio.com/try-twilio — trial account. You get a free trial balance.
   **Trial limits:** you may only call numbers you have verified in the console, and messages
   are prefixed with "Twilio trial". That is fine for a hackathon demo — put your teammates'
   numbers in `CONSENTED_NUMBERS`.

---

## How it works

```
FLEWS / CWC / IMD / Open-Meteo  (free, official)
        │  poll · every 15 min (GitHub Actions cron → POST /cron/ingest)
        ▼
   RiskEvent normaliser  ──► PostgreSQL 15 + PostGIS (Supabase)
        │  threshold breach in a revenue circle
        ▼
   AGENT A · WATCHDOG
        │  pick language per household → compose script (LLM)
        ▼
   Bhashini / Indic-TTS  ──►  MP3  ──►  Twilio IVR (<Play> + <Gather>)
        │                                        │
        │◄────────── speech reply (ASR) ◄────────┘
        ▼
   priority score + call outcome written to DB
        │  no answer?
        ▼
   retry ×3 (Redis, exponential backoff) ──► SMS to gaon-bura ──► DDMA escalation ticket
        │
        ▼   (after the flood, in the other direction)
   villager sends a WhatsApp voice note
        ▼
   AGENT B · TRIAGER  →  Whisper STT → LLM extraction → structured relief ticket
        ▼
   relief ops dashboard (MapLibre + OSM) — live call log, priority board, ticket queue
```

## What's in here

```
BaanMitra/
├── src/baanmitra/
│   ├── config.py              # free-tier settings from .env
│   ├── models.py              # RiskEvent · Household · Ticket
│   ├── db.py                  # SQLAlchemy + PostGIS spatial joins (Supabase)
│   ├── llm.py                 # Groq free tier (OpenAI-compatible) + Gemini fallback
│   ├── sources/               # FLEWS parser, CWC poller, Open-Meteo (no key needed)
│   ├── voice/
│   │   ├── tts.py             # Bhashini → Indic-TTS → ttsfree → gTTS fallback chain
│   │   ├── stt.py             # Groq whisper-large-v3 (free)
│   │   └── telephony.py       # Twilio trial IVR, retry + escalation policy
│   ├── agents/
│   │   ├── watchdog.py        # AGENT A — outbound alert agent
│   │   └── triager.py         # AGENT B — inbound distress triage agent
│   ├── api/main.py            # FastAPI: Twilio webhooks, cron hook, dashboard data
│   └── seed.py                # seed circles + synthetic households (no real PII)
├── doctor.py                  # system-requirements proof + missing-key checklist
├── smoke_test.py              # 9 offline checks, no keys needed
├── pyproject.toml             # `pip install -e .` makes `python -m baanmitra.*` work
├── dashboard/index.html       # MapLibre + OSM dashboard (free tiles)
├── data/revenue_circles.csv   # 12 flood-prone circles with coordinates
├── docs/                      # SETUP.md · technical_architecture.md · architecture.png
├── .github/workflows/ingest.yml   # free 15-minute cron (dry-run in CI, live when deployed)
└── COSTS.md                   # exact free-tier limits + what is deliberately excluded
```

## Safety rules baked into the code

- **`CONSENTED_NUMBERS`** — `watchdog` refuses to dial any number not in this allowlist.
- Every message names **ASDMA / CWC as the warning authority**; BaanMitra never presents
  itself as an official alert.
- Only **household IDs** (never names, never PII) are sent to any LLM prompt.
- Every escalation is **human-in-the-loop** — the agent prepares, a human confirms.

## Run the demo (90 seconds)

1. `.\.venv\Scripts\python.exe -m baanmitra.agents.watchdog --demo` — picks a seeded
   high-severity RiskEvent for a chosen circle.
2. Your verified phone rings → the alert plays in **Assamese** and asks
   *"আপোনালৈ সহায়্যৰ প্ৰয়োজন নে?"* (do you need help?).
3. Reply out loud — the reply is transcribed and the household is flagged **priority**.
4. Leave a second team member's phone unanswered → retries fire → escalation card appears
   on the dashboard.
5. Send a WhatsApp voice note to your Twilio sandbox number → it shows up as a structured,
   prioritised ticket.

## Documentation

- **[docs/SETUP.md](docs/SETUP.md)** — what to fix before it runs: every key, the Supabase
  session-pooler string, the Twilio trial limits, the public-URL step, and troubleshooting.
- **[COSTS.md](COSTS.md)** — every free tier, its limit, and the two paid sponsor tracks excluded.
- **[docs/technical_architecture.md](docs/technical_architecture.md)** —
  full architecture spec, schemas, agent pseudocode and the 24-hour build plan.
- **[docs/architecture.png](docs/architecture.png)** — the system architecture diagram.
