"""
config.py

Loads and validates all environment variables in one place, so every
other module just does `from config import settings` instead of calling
os.environ directly. Fails fast and clearly if something required is missing.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _split_models(name: str, default: str) -> list[str]:
    """Comma-separated env var -> ordered list of model IDs (fallback chain)."""
    raw = os.environ.get(name, default)
    return [m.strip() for m in raw.split(",") if m.strip()]


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    phone_number: str
    owner_id: int
    telegram_session: str

    database_url: str

    # --- Identity injected into the LLM system prompt (see llm.py) ---
    owner_name: str
    owner_bio: str

    # --- Text generation (Groq primary, OpenRouter as last-resort fallback) ---
    groq_api_key: str

    # --- Vision / image understanding (OpenRouter only) ---
    openrouter_api_key: str

    groq_text_models: list[str] = field(default_factory=list)
    openrouter_text_fallback_model: str = ""
    openrouter_vision_models: list[str] = field(default_factory=list)

    # --- Speech-to-text (Groq Whisper, tuned for Uzbek) ---
    groq_stt_models: list[str] = field(default_factory=list)
    stt_language: str = "uz"
    stt_prompt: str = ""

    owner_pause_minutes: int = 10
    short_history_limit: int = 6
    initial_reply_delay_seconds: int = 10

    # Flood protection: caps how many auto-replies the bot sends within a
    # rolling 1-hour window, so a stuck loop or a burst of messages can't
    # get the account flagged by Telegram.
    max_replies_per_hour_per_chat: int = 20
    max_replies_per_hour_global: int = 60


settings = Settings(
    api_id=int(_require("API_ID")),
    api_hash=_require("API_HASH"),
    phone_number=_require("PHONE_NUMBER"),
    owner_id=int(_require("OWNER_ID")),
    # Empty string is fine for the very first local run (generate_session.py
    # doesn't have one yet) — after that, this should always be set.
    telegram_session=os.environ.get("TELEGRAM_SESSION", ""),
    database_url=_require("DATABASE_URL"),
    owner_name=_require("OWNER_NAME"),
    owner_bio=_require("OWNER_BIO"),
    groq_api_key=_require("GROQ_API_KEY"),
    # Ordered fallback chain: tries each in order until one succeeds.
    # gpt-oss-120b = quality, gpt-oss-20b = speed/backup (llama-3.3-70b-versatile
    # was retired by Groq on 2026-08-16 — do not use it anymore).
    groq_text_models=_split_models(
        "GROQ_TEXT_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b"
    ),
    openrouter_api_key=_require("OPENROUTER_API_KEY"),
    # Last-resort text fallback if BOTH Groq models are down/rate-limited.
    openrouter_text_fallback_model=os.environ.get(
        "OPENROUTER_TEXT_FALLBACK_MODEL", "z-ai/glm-5.2:free"
    ),
    # Vision chain: two named free vision models, then openrouter/free — an
    # auto-router that picks whatever free model currently supports images,
    # so this last step keeps working even if a specific model ID gets
    # delisted (free model catalog rotates often).
    openrouter_vision_models=_split_models(
        "OPENROUTER_VISION_MODELS",
        "google/gemma-4-31b-it:free,"
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,"
        "openrouter/free",
    ),
    # whisper-large-v3 first: it's measurably more accurate than the
    # distilled -turbo variant on lower-resource languages like Uzbek,
    # which matters more here than turbo's speed edge. -turbo is the
    # fallback, used only if large-v3 itself errors out — a "succeeded but
    # transcribed badly" result isn't detectable as a failure, so ordering
    # by accuracy (not just availability) is what actually fixes quality.
    groq_stt_models=_split_models(
        "GROQ_STT_MODELS", "whisper-large-v3,whisper-large-v3-turbo"
    ),
    stt_language=os.environ.get("STT_LANGUAGE", "uz"),
    # Optional Whisper "prompt" hint (see transcribe.py) — free text that
    # primes vocabulary/spelling/style. Defaults to one built from
    # OWNER_NAME/OWNER_BIO if left unset.
    stt_prompt=os.environ.get("STT_PROMPT", ""),
    owner_pause_minutes=int(os.environ.get("OWNER_PAUSE_MINUTES", 10)),
    short_history_limit=int(os.environ.get("SHORT_HISTORY_LIMIT", 6)),
    initial_reply_delay_seconds=int(os.environ.get("INITIAL_REPLY_DELAY_SECONDS", 5)),
    max_replies_per_hour_per_chat=int(os.environ.get("MAX_REPLIES_PER_HOUR_PER_CHAT", 30)),
    max_replies_per_hour_global=int(os.environ.get("MAX_REPLIES_PER_HOUR_GLOBAL", 60)),
)
