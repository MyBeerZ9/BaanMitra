"""Free-tier configuration.

Everything here is a free tier. No credit card is required for any setting.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.database_url: str = os.getenv("DATABASE_URL", "")
        self.redis_url: str = os.getenv("REDIS_URL", "")

        # LLM + STT (Groq free tier, no card)
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "")
        self.llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        self.llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
        self.stt_model: str = os.getenv("STT_MODEL", "whisper-large-v3")

        # Optional fallback LLM (Google AI Studio free tier, no card)
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        # TTS providers (all free)
        self.bhashini_api_key: str = os.getenv("BHASHINI_API_KEY", "")
        self.bhashini_user_id: str = os.getenv("BHASHINI_USER_ID", "")
        self.ttsfree_api_key: str = os.getenv("TTSFREE_API_KEY", "")

        # Twilio trial (no card; verified numbers only)
        self.twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_number: str = os.getenv("TWILIO_NUMBER", "")
        self.twilio_trial: bool = os.getenv("TWILIO_TRIAL", "true").lower() == "true"

        # Safety: the agent may ONLY dial numbers in this allowlist.
        raw = os.getenv("CONSENTED_NUMBERS", "")
        self.consented_numbers: set[str] = {
            n.strip() for n in raw.split(",") if n.strip()
        }

        self.public_base_url: str = os.getenv(
            "PUBLIC_BASE_URL", "http://localhost:8000"
        ).rstrip("/")
        self.cron_token: str = os.getenv("CRON_TOKEN", "change-me")

        self.audio_dir: str = os.getenv("AUDIO_DIR", "audio_cache")
        self.escalation_attempts: int = int(os.getenv("ESCALATION_ATTEMPTS", "3"))

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n, "")]
        if missing:
            raise RuntimeError(
                "Missing free-tier configuration: "
                + ", ".join(missing)
                + ". See .env.example - all of these are FREE tiers."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
