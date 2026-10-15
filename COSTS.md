# COSTS.md — what is free, what it costs, and what is deliberately excluded

**Budget for this project: ₹0 / $0. No credit card anywhere.**

---

## 1. Free tiers actually used

| Service | Used for | Free limit (verified Oct 2026) | Card? |
|---|---|---|---|
| **Groq** | LLM reasoning + Whisper STT | chat models ~30 req/min, ~1,000 req/day; `whisper-large-v3` 20 req/min, **2,000 req/day**, 7,200 audio-sec/hour (~8 h audio/day) | ❌ none |
| **Supabase** | PostgreSQL 15 + PostGIS | 500 MB database, 2 GB egress, realtime included | ❌ none |
| **Upstash** | Redis (retries, idempotency, rate limits) | 10,000 commands/day | ❌ none |
| **Bhashini** | Assamese / Bodo / Bengali TTS | free for registered users (Govt. of India national language mission) | ❌ none |
| **AI4Bharat Indic-TTS** | offline Assamese / Bodeo TTS | MIT-licensed, runs on your laptop, unlimited | ❌ none |
| **ttsfree.in** | optional TTS API | 200 AI credits/month ≈ 20,000 characters | ❌ none |
| **Twilio (trial)** | outbound calls, WhatsApp sandbox | trial balance; **verified numbers only**; "trial" message prefix | ❌ none |
| **Render** | API hosting | 750 instance-hours/month free web service (sleeps after 15 min idle) | ❌ none |
| **GitHub Actions** | 15-minute ingest cron | unlimited on public repos, 2,000 min/month on private | ❌ none |
| **Open-Meteo** | rainfall forecasts | free, **no API key at all** | ❌ none |
| **MapLibre + OSM/CARTO** | dashboard map | free tiles, no key | ❌ none |
| **Google AI Studio (optional)** | fallback LLM | Gemini free tier | ❌ none |

**Free-software licences relied on:** AI4Bharat Indic-TTS (MIT), IndicF5 / vits_rasa_13
(Apache-2.0), Whisper (MIT, via Groq), FastAPI/Starlette (BSD), SQLAlchemy (MIT),
Twilio helper (MIT), MapLibre (BSD).

---

## 2. Deliberately EXCLUDED because they cost money

| Excluded | Why | Cost |
|---|---|---|
| **Agent37 Cloud** (the ₹1,000 cash + $10 credits-per-project track) | sandboxes are billed per minute; a card must be on file before you get the $5 starter credit | paid |
| **Nodus compute** (the ₹50k / ₹30k / ₹20k Nodus Challenge) | paid execution layer for AI workloads | paid |
| **ElevenLabs** | free tier is only 10,000 characters/month **and has no Assamese or Bodo voices** — so it loses on both cost *and* language | limited free |
| **GPT-4 / Claude / OpenAI API** | paid | paid |
| **AWS / Azure / GCP TTS** | require billing accounts even for "free" tiers | card |

### Note on the hackathon prize tracks
Because Agent37 and Nodus are excluded, this free build targets the **main event prizes**
(₹60,000 / ₹37,500 / ₹25,000) and the **category awards** — Best Use of AI Agents, Best Social
Impact Build, Most Fundable Build, Best Developer Tool, Best Design & Craft, Best First-Time
Team, Best Technically Impressive. The ₹1,000-per-project Agent37 track needs credits, so it
is skipped unless you add a card later.

---

## 3. Hard limits you must design around (free-tier realities)

1. **Twilio trial can only call verified numbers.** Put every team member's number in
   `CONSENTED_NUMBERS` *and* verify it in the Twilio console. Never dial real villagers during
   the hackathon.
2. **Twilio `<Say>` has no Assamese voice.** So the pipeline is: TTS → MP3 → `<Play>`.
   That is also how production systems do it.
3. **Groq rate limits are per model.** 1,000 LLM requests/day is plenty for a demo, but add
   retry-with-backoff (already in `voice/stt.py` and `llm.py`).
4. **Render free services sleep** after 15 minutes of inactivity. Use the GitHub Actions cron
   to warm it (`/healthz`) before ingest, and expect a ~30 s cold start.
5. **Supabase free projects pause** after 1 week of inactivity — just open the dashboard to
   wake it.
6. **Assamese TTS quality varies by provider.** The fallback chain in `voice/tts.py`
   (Bhashini → Indic-TTS → ttsfree → gTTS) exists precisely so the demo never dies on stage.

---

## 4. Total cost

| Item | Cost |
|---|---|
| Development (Windows, Python 3.12+, Node 24, VS Code) | ₹0 |
| All APIs listed in section 1 | ₹0 |
| Public repo + GitHub Actions cron | ₹0 |
| Hackathon entry (Hackyard Build 2026) | ₹0 |
| **Total** | **₹0** |
