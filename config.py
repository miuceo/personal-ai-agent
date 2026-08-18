"""
config.py

Loads and validates all environment variables in one place, so every
other module just does `from config import settings` instead of calling
os.environ directly. Fails fast and clearly if something required is missing.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    phone_number: str
    owner_id: int
    telegram_session: str

    database_url: str

    openrouter_api_key: str
    openrouter_model: str
    openrouter_fallback_model: str

    groq_api_key: str
    groq_stt_model: str

    owner_pause_minutes: int
    short_history_limit: int
    initial_reply_delay_seconds: int

    # Flood protection: caps how many auto-replies the bot sends within a
    # rolling 1-hour window, so a stuck loop or a burst of messages can't
    # get the account flagged by Telegram.
    max_replies_per_hour_per_chat: int
    max_replies_per_hour_global: int


settings = Settings(
    api_id=int(_require("API_ID")),
    api_hash=_require("API_HASH"),
    phone_number=_require("PHONE_NUMBER"),
    owner_id=int(_require("OWNER_ID")),
    # Empty string is fine for the very first local run (generate_session.py
    # doesn't have one yet) — after that, this should always be set.
    telegram_session=os.environ.get("TELEGRAM_SESSION", ""),
    database_url=_require("DATABASE_URL"),
    openrouter_api_key=_require("OPENROUTER_API_KEY"),
    openrouter_model=os.environ.get("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free"),
    openrouter_fallback_model=os.environ.get(
        "OPENROUTER_FALLBACK_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
    ),
    groq_api_key=_require("GROQ_API_KEY"),
    groq_stt_model=os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo"),
    owner_pause_minutes=int(os.environ.get("OWNER_PAUSE_MINUTES", 10)),
    short_history_limit=int(os.environ.get("SHORT_HISTORY_LIMIT", 6)),
    initial_reply_delay_seconds=int(os.environ.get("INITIAL_REPLY_DELAY_SECONDS", 10)),
    max_replies_per_hour_per_chat=int(os.environ.get("MAX_REPLIES_PER_HOUR_PER_CHAT", 20)),
    max_replies_per_hour_global=int(os.environ.get("MAX_REPLIES_PER_HOUR_GLOBAL", 60)),
)
