# BaanMitra — setup guide: what to fix before it runs

**Total cost: Rs 0. No credit card is required for any step on this page.**

Run this first, at any time:

```powershell
.\.venv\Scripts\python.exe doctor.py
```

It prints your machine's requirements proof (OS, RAM, disk, Python, internet)
and the exact list of keys still missing. Everything below is what it is telling you.

---

## 0. It already runs without any key

```powershell
.\.venv\Scripts\python.exe smoke_test.py                 # 9/9 offline checks
.\.venv\Scripts\python.exe -m baanmitra.agents.watchdog --dry-run
.\.venv\Scripts\python.exe -m baanmitra.api.main
start http://localhost:8000/dashboard/
```

With no keys you get: live data collection (FLEWS + CWC + Open-Meteo), the
conservative threshold engine, **hardcoded 5-language alert templates**, gTTS
audio, the dashboard shell, and a hard **consent gate** that refuses to dial
anybody. What you do **not** get: real phone calls, LLM-quality wording,
transcribed replies, or saved history.

---

## 1. Groq — brain + ears (5 minutes, free, no card)

<https://console.groq.com/keys> → sign in with email → **Create API key**.

```
GROQ_API_KEY=gsk_...
```

Unlocks: LLM-written alert scripts in Assamese/Bodo/Bengali/Hindi/English, and
Whisper `whisper-large-v3` transcription of the villager's spoken reply and of
WhatsApp voice notes. One key does both.

---

## 2. Twilio — the phone (trial, no card)

<https://twilio.com/try-twilio> → Dashboard → Account SID / Auth Token →
Phone Numbers → get a number.

```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_NUMBER=+1xxxxxxxxxx
CONSENTED_NUMBERS=+91xxxxxxxxxx,+91yyyyyyyyyy
```

**Trial limits you will hit — plan around them:**

| Limit | What to do |
|---|---|
| You may only call **verified** numbers | Console → *Caller IDs* → verify each teammate's number (they answer a call and type a code) |
| Calls are prefixed with a trial message | Fine for a hackathon demo |
| WhatsApp only works in the **sandbox** | Message the sandbox number to join it |

`CONSENTED_NUMBERS` is a safety allowlist: the agent refuses to dial anything
that is not on it, and it must be in E.164 format (`+91` + 10 digits).

---

## 3. Supabase — the memory (free project, no card)

1. <https://supabase.com> → sign in with GitHub → **New project** → plan **Free**.
   Region: `ap-south-1` (Mumbai). Set a database password you will remember.
2. Wait ~2 minutes for provisioning.
3. **SQL Editor** → paste the DDL and **Run**:

   ```powershell
   .\.venv\Scripts\python.exe -m baanmitra.db --init
   ```

   The first line (`create extension if not exists postgis;`) enables **PostGIS**,
   which Supabase pre-installs on every plan including free. If it errors, go to
   *Database → Extensions* and toggle `postgis` on, then re-run.
4. **Connect** button (top bar) → **Session pooler** tab → copy the string.

```
DATABASE_URL=postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@[POOLER-HOST]:5432/postgres?sslmode=require
```

Three things people get wrong (the doctor checks all three):

| Mistake | Why it breaks | Fix |
|---|---|---|
| Using the **direct** string (`db.[ref].supabase.co:5432`) | On the free plan that endpoint is **IPv6-only**, so from an IPv4 network it just times out | Use the **session pooler** string |
| Using the **transaction** pooler (port **6543**) | It does not support prepared statements, which SQLAlchemy issues | Use the session pooler (port 5432) |
| Password with `& # ?` or a space | Breaks the URL | Percent-encode it (`%20` etc.) and add `?sslmode=require` |

The session-pooler username is `postgres.[PROJECT-REF]` (with the ref), not `postgres`.

5. Seed it — 12 flood-prone revenue circles + synthetic households (**no real PII**):

   ```powershell
   .\.venv\Scripts\python.exe -m baanmitra.seed
   ```

Without `DATABASE_URL` the project still runs, but every call/ticket is lost on
restart and the dashboard shows an empty history plus `db_error`.

---

## 4. Upstash — retry counters (free, optional)

<https://upstash.com> → *Create database* (free tier, region Mumbai) → copy the
`rediss://` URL into `REDIS_URL`. Without it, escalation counters live in RAM
and reset when the process restarts — acceptable for a demo.

---

## 5. Bhashini — real Assamese and Bodo voices (free, govt)

<https://bhashini.gov.in> → register → API key + user id:

```
BHASHINI_API_KEY=...
BHASHINI_USER_ID=...
```

This matters more than it sounds: the gTTS fallback **cannot pronounce Assamese
properly**. The chain is `Bhashini → AI4Bharat Indic-TTS (local, MIT) → ttsfree → gTTS`.
If your machine has under ~2 GB free RAM, skip the local Indic-TTS option (it
pulls ~2 GB of torch) and use Bhashini instead — `doctor.py` warns about this.

---

## 6. Make it callable by Twilio (the step everyone forgets)

Twilio must be able to **fetch your audio over the public internet**:

```
PUBLIC_BASE_URL=https://your-public-host      # NOT http://localhost:8000
CRON_TOKEN=some-long-random-string
```

| Option | How | Cost |
|---|---|---|
| ngrok (quickest) | `ngrok http 8000` → paste the `https://xxxx.ngrok-free.app` URL | free tier |
| Render (proper) | Deploy this repo as a Web Service, start command `uvicorn baanmitra.api.main:app --host 0.0.0.0 --port $PORT` | free tier |

If you skip this, the phone rings, the villager answers… and hears silence,
because Twilio cannot download `PUBLIC_BASE_URL/audio/…`.

### Then switch the cron on

GitHub → your repo → **Settings → Secrets and variables → Actions** → add
`BAANMITRA_URL`, `CRON_TOKEN`, `GROQ_API_KEY`, `DATABASE_URL`. The workflow
`.github/workflows/ingest.yml` automatically uses live mode once `BAANMITRA_URL`
exists; until then it safely runs a **dry-run** on the GitHub runner every 15
minutes and posts the result to the run summary. CI can never place a call.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `CONSENTED_NUMBERS is empty …` warning | Safety gate | Put verified numbers in `.env` |
| `skip +91… (not in CONSENTED_NUMBERS)` | Household not allowlisted | Add the number or seed with a matching prefix |
| Call connects, no audio | `PUBLIC_BASE_URL` is localhost | Section 6 |
| `DATABASE_URL is not set` on the dashboard | No Supabase | Section 3 (dashboard degrades, it does not crash) |
| `LLM script unavailable … using template` | No `GROQ_API_KEY` | Section 1 — the demo still works |
| `no free TTS provider produced audio` | All TTS providers dead | Set `BHASHINI_API_KEY`, or check internet for gTTS |
| Workflow red X on GitHub | You are on the old workflow | Pull the latest commit (it now degrades to runner mode) |
