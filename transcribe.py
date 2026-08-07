"""
transcribe.py

Converts Telegram voice notes to text using Groq's hosted Whisper API,
so voice messages can flow through the same text-based reply pipeline
as everything else.
"""

import httpx

from config import settings

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    files = {"file": (filename, audio_bytes, "audio/ogg")}
    data = {"model": settings.groq_stt_model}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_STT_URL, headers=headers, files=files, data=data)
        if resp.status_code >= 400:
            raise RuntimeError(f"Groq STT error {resp.status_code}: {resp.text}")
        result = resp.json()

    return result.get("text", "").strip()