# BaanMitra (বানমিত্ৰা) — Technical Architecture

**The last mile of India's flood early warning system**
Hackyard Build 2026 · 24-hour in-person hackathon · IIT Guwahati · 24–25 October 2026

> *Every existing system forecasts the flood. None of them talks to the villager.*

---

## 1. What the system does, in one paragraph

BaanMitra is an always-on, multilingual, voice-first AI agent layer that sits **on top of**
India's official flood-forecasting stack (FLEWS, CWC, IMD, SACHET). It converts an official
forecast into an **outbound phone call to at-risk households in their own language**, asks two
safety questions, records a **priority score**, retries and **escalates** unanswered calls up the
gaon-bura → DDMA chain, and turns **inbound WhatsApp voice notes** after the flood into
structured, geotagged relief tickets for the control room. Official forecasts are accurate
(89%, 12–48 h lead time); what fails is delivery to the citizen. BaanMitra is that layer.

---

## 2. Layer-by-layer architecture

### Layer 1 — Data & signal sources (read-only, official)
| Source | Endpoint / channel | What we take |
|---|---|---|
| FLEWS (NESAC + ASDMA) | `asdma.gov.in` flood-alert pages | revenue-circle alerts, severity class, valid window |
| CWC Level Forecast | `ffs.india-water.gov.in` | 200 level stations + 150 inflow reservoirs, water level vs danger level |
| CWC 7-day Advisory | `aff.india-water.gov.in` | basin-scale rainfall-runoff advisories |
| IMD | imd.gov.in / Mausam API | rainfall nowcasts, Doppler radar, district forecasts |
| Open-Meteo / Google Flood Hub | `api.open-meteo.com` · Flood Forecasting API | independent cross-check, "virtual gauge" points |
| NDMA SACHET (CAP) | `sachet.ndma.gov.in` RSS/CAP | official Common Alerting Protocol feed — consumed, never re-issued |

**Rule:** BaanMitra never becomes a warning authority. It cites ASDMA / CWC on every message.

### Layer 2 — Ingestion & normalisation
Python 3.12 pollers running as **Render cron jobs every 15 minutes**:
- **FLEWS parser** — BeautifulSoup + pdfplumber turns bulletin pages/PDFs into structured alert objects.
- **Feed pollers** — `httpx` async clients pull CWC / IMD / Open-Meteo JSON into pydantic-typed models.
- **RiskEvent normaliser** — all sources collapse into one schema:
  ```
  RiskEvent {
    id: uuid
    revenue_circle: str          # e.g. Bongaigaon / Sidli
    villages: [str]
    river: str
    level_vs_danger: float       # metres above danger level
    severity: flood_watch | low | moderate | high | very_high
    valid_from / valid_to: datetime
    lead_time_h: float
    source_refs: [url]           # provenance for judges & auditors
    affected_households: [uuid]  # resolved via PostGIS spatial join
  }
  ```
- **CAP listener** — subscribes to SACHET's CAP feed so official alerts flow in automatically.

### Layer 3 — Intelligence: two agents in Agent37 persistent sandboxes
**Agent37 Cloud (YC F26)** hosts each agent in its own isolated, *persistent* sandbox with cron
scheduling, per-minute billing, and files that survive between runs. This is a hackathon
sponsor track: **₹1,000 cash + $10 credits per verified project, no in-person attendance
required** (verification needs the project link, application email, Agent37 account email,
instance ID and a dashboard screenshot).

**Agent A · WATCHDOG (outbound)**
```
cron() every 15 min
  └─ load new RiskEvents since last run
  └─ rule engine + LLM reasoning (Claude / Gemini API):
        is this a real breach? is it new? which circles?
  └─ spatial join → affected households (PostGIS)
  └─ for each household:
        pick language (Assamese / Bodo / Bengali / Hindi / English)
        compose the script  →  trigger call (Twilio)
        parse <Gather> ASR of the reply
        priority score = f(elderly, disabled, livestock, mobility, distance to river)
        persist outcome: PENDING → CALLING → ANSWERED / NO_ANSWER → ESCALATED
```

**Agent B · TRIAGER (inbound)**
```
WhatsApp voice note arrives
  └─ Whisper / ElevenLabs STT  → text
  └─ LLM extraction: intent, location, severity, needs, people count
  └─ dedupe + merge against open tickets
  └─ write structured relief ticket + geotag to PostgreSQL
  └─ push to dashboard via Socket.IO
```

**Persistent household memory** — per-household JSON lives in the sandbox's persistent
storage, so the *second* warning in a season is informed by the first (who has an elderly
member, who was unreachable last time). Mirrored into PostgreSQL for the dashboard.

### Layer 4 — Voice & telephony
| Component | Role |
|---|---|
| **ElevenLabs** | multilingual TTS (Assamese, Bodo, Bengali, Hindi) + STT; sponsor tracks: Creator per participant, Pro for the overall winner, Scale for "Best Project Built with ElevenLabs" |
| **Twilio Programmable Voice** | outbound PSTN call, `<Gather>` speech recognition, DTMF fallback, Status Callbacks |
| **Twilio WhatsApp Business API** | inbound voice notes, outbound confirmation + shelter/helpline messages |
| **Escalation policy engine** | 3 attempts with exponential backoff → gaon-bura SMS → DDMA control-room ticket |

Voice-first by design: works on a ₹1,500 feature phone, no app, no smartphone, no literacy bar.

### Layer 5 — Application & state
- **FastAPI** (async Python, pydantic) — REST + webhooks, deployed on **Nodus compute (YC F26)**,
  which is also the **Nodus Challenge** track (₹50,000 / ₹30,000 / ₹20,000 for the top three teams
  building on Nodus compute at the event; $30 credits per event team).
- **PostgreSQL 15 + PostGIS** — `households`, `revenue_circles`, `risk_events`, `calls`,
  `tickets`, village polygons for the spatial join.
- **Redis** — retry/escalation queue, idempotency keys, per-second rate limits.
- **Render + Render Workflows** — web hosting plus durable background jobs (ingest cron,
  retries, escalation fan-out). Also the "Best Use of Render Workflows" track
  ($200/$100/$50 credits per member).

### Layer 6 — Relief ops dashboard
Next.js 14 + React + TypeScript + Tailwind, MapLibre GL for the revenue-circle/village layers,
Recharts for metrics, Socket.IO for live push.
- **Live call log** — answered / no-answer / unreachable, with recordings and transcripts.
- **Priority board + map** — household priority list, relief-camp and helpline overlays.
- **Ticket queue + analytics** — triaged distress tickets, confirmed-reach rate, median
  bulletin → confirmed minutes, tickets triaged per hour.

### Cross-cutting
- **Observability** — structlog JSON, OpenTelemetry traces, call recordings, Sentry, Grafana.
- **Security & privacy** — consent registry; **household IDs only in LLM prompts, never PII**;
  TLS 1.3; dashboard RBAC.
- **Safety** — consented/test numbers only during the hackathon; ASDMA/CWC cited as the warning
  authority; human-in-the-loop on every escalation.
- **Verification artefacts** — Agent37 instance ID + dashboard screenshot, Render service ID,
  Nodus deployment manifest.

---

## 3. Data flow (end to end)

```
FLEWS / CWC / IMD / Open-Meteo
        │  poll · 15 min
        ▼
   RiskEvent normaliser ──► PostgreSQL (risk_events)
        │  threshold breach in revenue circle X
        ▼
   AGENT A · WATCHDOG (Agent37 sandbox, cron)
        │  select households · pick language · compose script
        ▼
   ElevenLabs TTS ──► Twilio Voice IVR ──► 📞 villager's phone
        │                                        │
        │                              <Gather> ASR reply
        │                                        │
        │◄────────────── understanding ◄─────────┘
        ▼
   priority score + outcome written to PostgreSQL
        │  no answer?
        ▼
   retry ×3 (exponential backoff) ──► gaon-bura SMS ──► DDMA ticket
        │
        ▼  (post-flood, from the other direction)
   villager sends WhatsApp voice note
        ▼
   AGENT B · TRIAGER (Agent37 sandbox)
        │  STT → LLM extraction → dedupe/merge
        ▼
   structured relief ticket + geotag ──► dashboard ticket queue
```

---

## 4. Tech stack summary

| Layer | Technology | Why this one |
|---|---|---|
| Agent runtime | **Agent37 Cloud (YC F26)** | persistent per-agent sandboxes, cron, per-minute billing — hosts both agents and satisfies the ₹1,000/verified-project track |
| Compute | **Nodus (YC F26)** | intelligent execution layer for AI workloads; Nodus Challenge track (₹1,00,000 pool) |
| Voice | **ElevenLabs** | multilingual TTS/STT incl. Assamese; Creator/Pro/Scale sponsor tracks |
| Telephony | **Twilio** Programmable Voice + WhatsApp | real PSTN reach, `<Gather>` ASR, Status Callbacks, WhatsApp voice notes |
| Backend | **FastAPI** (Python 3.12, pydantic, SQLAlchemy 2, asyncpg) | async, typed, fast to build in 24 h |
| Database | **PostgreSQL 15 + PostGIS** | relational state + village geometry spatial joins |
| Queue/cache | **Redis** + RQ | retries, idempotency, rate limits |
| Hosting/jobs | **Render** web services + **Render Workflows** | zero-ops deploy + durable background jobs (sponsor track) |
| Frontend | **Next.js 14** + React + TS + Tailwind + MapLibre GL + Recharts | fast dashboard, live updates via Socket.IO |
| LLMs | **Claude / Gemini API** (via Agent37 gateway or direct) | threshold reasoning, script composition, ticket extraction |
| Data | FLEWS, CWC, IMD, Open-Meteo, Google Flood Hub, SACHET CAP | all official or free |
| Observability | structlog, OpenTelemetry, Sentry, Grafana | judge-friendly dashboards |

---

## 5. Repository structure

```
baanmitra/
├── ingestion/
│   ├── flews_parser.py        # BeautifulSoup + pdfplumber
│   ├── pollers.py             # httpx async clients
│   ├── cap_listener.py        # SACHET CAP feed
│   └── normaliser.py          # → RiskEvent pydantic model
├── agents/
│   ├── watchdog/              # Agent A: cron, rules, LLM, call orchestration
│   │   ├── main.py
│   │   ├── rules.py
│   │   ├── priority.py
│   │   └── memory.py          # sandbox persistent files
│   └── triager/               # Agent B: STT, extraction, dedupe, tickets
├── api/                       # FastAPI: households, webhooks, dashboard API
├── voice/
│   ├── tts.py                 # ElevenLabs multilingual
│   └── ivr.py                 # Twilio <Gather>, escalation policy
├── dashboard/                 # Next.js 14 app
├── infra/
│   ├── render.yaml            # web + cron + workflows
│   ├── nodus/                 # deployment manifest for Nodus compute
│   └── agent37/               # sandbox templates + instance IDs
└── scripts/
    ├── seed_households.py     # synthetic households on real revenue circles
    └── verify_agent37.py      # captures instance ID + dashboard screenshot
```

---

## 6. How to build it (order of work, 24-hour plan)

| Phase | Hours | Work |
|---|---|---|
| 0. De-risk | H0–H2 | Validate ElevenLabs Assamese/Bodo TTS **first**; stand up Agent37 sandboxes + instance ID; Twilio verified caller |
| 1. Data | H2–H5 | FLEWS + CWC pollers → RiskEvent schema; seed 3 villages with synthetic households on real circles |
| 2. Agent A | H5–H10 | cron loop, threshold rule, household selection, script composition, outbound call |
| 3. Voice loop | H10–H14 | `<Gather>` ASR → priority score → outcome persistence → escalation state machine |
| 4. Agent B | H14–H18 | WhatsApp inbound → STT → LLM extraction → ticket + dashboard feed |
| 5. Ship | H18–H22 | Deploy on Nodus compute + Render Workflows; capture verification artefacts |
| 6. Rehearse | H22–H24 | Rehearse the 90-second demo twice; record a backup video in case live calls fail |

**Team split (2–4 people):** ① agents/backend + Agent37/Nodus ② voice/IVR + ElevenLabs + Twilio
③ dashboard + triage pipeline ④ pitch, demo, prize-submission paperwork.

---

## 7. Sponsor-track alignment

| Track | Requirement | Status |
|---|---|---|
| **Agent37** — ₹1,000 cash + $10 credits per verified project (up to 300 projects) | verified real use of Agent37 sandboxes; **no in-person attendance required** | both agents run in Agent37 sandboxes; instance ID + dashboard screenshot captured |
| **Nodus Challenge** — ₹50k / ₹30k / ₹20k | build on Nodus compute at the in-person event | FastAPI + agent execution deployed on Nodus |
| **ElevenLabs** — Creator / Pro / Scale | use ElevenLabs voice | all TTS/STT via ElevenLabs, multilingual |
| **Render Workflows** — $200/$100/$50 per member | use Render Workflows | ingest cron, retries, escalation fan-out |
| **Hackyard LLM credits** — $100 per selected project | selected project | — |
| Categories: Best Use of AI Agents · Best Social Impact · Most Fundable · Best Developer Tool | two-agent voice system, Assam-specific, clear SDMA/NGO buyer path |

---

## 8. References

1. FLEWS (NESAC) — https://nesac.gov.in/scientific-programmes/disaster-management-support/
2. ASDMA flood warning — https://asdma.gov.in/project_flood_warning.html
3. FLEWS evaluation, *J. Earth Syst. Sci.* 2025 — https://www.ias.ac.in/article/fulltext/jess/134/0219
4. CWC flood forecasting (NIDM deck) — https://nidm.gov.in/pdf/acrc26/Preparatory%20Session/2.%20CWC.pdf
5. CWC 7-day advisory — https://aff.india-water.gov.in/ · station levels — https://ffs.india-water.gov.in/
6. SACHET national alert portal — https://sachet.ndma.gov.in/
7. GSMA case study on SACHET (over-alerting, 160-char limits) — https://www.gsma.com/solutions-and-impact/connectivity-for-good/mobile-for-development/wp-content/uploads/2025/05/Indias-SACHET-Public-Warning-System.pdf
8. Assam Flood Watch (existing bilingual dashboard) — https://assamfloodwatch.com/
9. Google Flood Hub — https://cities.google/flood-hub · API — https://developers.google.com/flood-forecasting
10. Oxfam: WhatsApp warnings from Bhutan save lives in Assam — https://www.oxfamindia.org/news/early-warning-whatsapp-messages-bhutan-save-lives-assam
11. Hackyard Build 2026 — https://hackyard.org/build2026 · Agent37 challenge — https://hackyard.org/build2026/agent37
12. Agent37 Cloud — https://www.agent37.com/cloud · Nodus (YC F26) — https://www.ycombinator.com/companies/nodus
