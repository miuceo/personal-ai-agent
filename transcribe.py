"""
transcribe.py

Converts Telegram voice notes to text using Groq's hosted Whisper API, so
voice messages can flow through the same text-based reply pipeline as
everything else.

Tuned for Uzbek: the `language` parameter is passed explicitly (ISO-639-1
"uz") so Whisper doesn't have to auto-detect the language, which improves
both accuracy and latency, and avoids the model occasionally mis-detecting
a short/mixed-language clip as e.g. Russian or Turkish and translating it
oddly.

Tries each model in settings.groq_stt_models in order (default:
whisper-large-v3-turbo, then whisper-large-v3) so a single model outage or
rate limit doesn't fail the whole voice-message flow.
"""

import logging

import httpx

from config import settings

log = logging.getLogger("secretary.transcribe")

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class _SttError(Exception):
    """A single STT model call failed. `retryable` mirrors llm.ProviderError:
    a 429/5xx or network error is worth trying the next model for, but a
    4xx (e.g. corrupt/oversized audio) will fail identically on every model,
    so don't repeat a 60s-timeout request that can't succeed."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


async def _transcribe_with_model(model: str, audio_bytes: bytes, filename: str) -> str:
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    files = {"file": (filename, audio_bytes, "audio/ogg")}
    data = {"model": model, "language": settings.stt_language}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(GROQ_STT_URL, headers=headers, files=files, data=data)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise _SttError(f"network error ({model}): {exc}", retryable=True) from exc

    if resp.status_code >= 400:
        retryable = resp.status_code == 429 or resp.status_code >= 500
        raise _SttError(
            f"Groq STT error {resp.status_code} ({model}): {resp.text[:300]}", retryable=retryable
        )

    result = resp.json()
    return result.get("text", "").strip()


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    if not settings.groq_stt_models:
        raise RuntimeError("No STT models configured (GROQ_STT_MODELS is empty)")

    last_error: Exception | None = None
    for model in settings.groq_stt_models:
        try:
            return await _transcribe_with_model(model, audio_bytes, filename)
        except _SttError as exc:
            log.warning("STT model failed (%s): %s", model, exc)
            last_error = exc
            if not exc.retryable:
                break
            continue

    # All STT models failed (or the request itself was bad) — raise so
    # main.py's existing handler sends the "ovozli xabaringizni tushunolmadim"
    # reply instead of hanging silently.
    raise RuntimeError(f"All Groq STT models failed. Last error: {last_error}")
