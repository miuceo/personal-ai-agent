"""
llm.py

OpenRouter chat completion wrapper. Supports:
- Plain text replies
- Image understanding (vision), for models that support it
- Three behavior "tiers" (owner / known_contact / stranger), each with a
  slightly different system prompt, matching how a real secretary would
  adjust tone depending on who they're talking to.
"""

import json
from typing import Any, Optional

import httpx

from config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

BASE_RULES = """\
Sen — hisob egasining shaxsiy raqamli kotibisan (AI agent). Odamlar unga Telegram orqali \
yozishadi, sen esa uning nomidan avtomatik javob berasan.

UMUMIY QOIDALAR:
- Foydalanuvchi qaysi tilda yozgan bo'lsa (o'zbek, rus, ingliz va h.k.), aynan o'sha tilda javob ber.
- Faqat senga berilgan xotira va yangi xabar (yoki rasm) asosida javob ber — bilmagan narsani \
o'ylab topma.
- Javobing juda uzun bo'lmasin — Telegram xabari uchun qulay, 2-4 gap yetarli.
- Agar suhbatdosh sendan "sen kimsan" yoki "bu AI/botmi" deb to'g'ridan-to'g'ri so'rasa, buni \
yashirma — halol tan ol, siz AI yordamchisisiz.
"""

TIER_PROMPTS = {
    # The account owner talking to their own secretary — full context, direct tone.
    "owner": BASE_RULES + """
BU SUHBATDOSH — HISOB EGASINING O'ZI (admin). Unga to'g'ridan-to'g'ri, ishonchli ohangda javob \
ber, xuddi shaxsiy yordamchisi kabi. U sendan hisobot, tushuntirish yoki buyruq so'rashi mumkin.
""",
    # Someone with prior message history — warm, memory-aware.
    "known_contact": BASE_RULES + """
BU SUHBATDOSH — ILGARI YOZGAN, TANISH ODAM. Xotiradagi ma'lumotlardan foydalanib, iliq va \
tabiiy javob ber, xuddi ular bilan avvaldan tanishgandek.
""",
    # First-time sender — a bit more careful/formal, and important matters get escalated.
    "stranger": BASE_RULES + """
BU SUHBATDOSH — BIRINCHI MARTA YOZAYOTGAN, NOTANISH ODAM. Xushmuomala, lekin biroz rasmiyroq \
va ehtiyotkor bo'l. Agar masala muhim yoki shoshilinch bo'lsa (uchrashuv so'rovi, muhim taklif, \
to'lov va h.k.), buni albatta ta'kidlab, hisob egasi tez orada shaxsan javob berishini ayt.
""",
}

JSON_FORMAT_INSTRUCTION = """
JAVOB FORMATI — FAQAT quyidagi JSON obyekti, boshqa hech qanday matn yoki markdown belgisi qo'shma:
{"reply": "foydalanuvchiga yuboriladigan javob matni", "memory_summary": "yangilangan xotira \
xulosasi: avvalgi xulosa + shu suhbatdan chiqqan muhim faktlar. Qisqa va tartibli, 400 so'zdan \
oshmasin."}
"""


def _build_user_content(
    user_name: str,
    memory_summary: str,
    recent_messages: list[dict],
    new_message: str,
    image_base64: Optional[str],
) -> Any:
    history_text = "\n".join(
        f"{'Foydalanuvchi' if m['role'] == 'user' else 'Kotib'}: {m['text']}"
        for m in recent_messages
    )
    text_block = (
        f"OLDINGI XOTIRA XULOSASI: {memory_summary or 'Hali yo\u2018q — bu birinchi suhbat.'}\n"
        f"OXIRGI XABARLAR:\n{history_text or 'Yo\u2018q'}\n"
        f"FOYDALANUVCHI ISMI: {user_name or 'Noma\u2018lum'}\n"
        f"YANGI XABAR: {new_message or '(rasm yuborildi, matn yo\u2018q)'}"
    )

    if image_base64 is None:
        return text_block

    # Vision-capable multimodal payload (OpenAI-compatible format, used by OpenRouter).
    return [
        {"type": "text", "text": text_block},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
    ]


async def generate_reply(
    tier: str,
    user_name: str,
    memory_summary: str,
    recent_messages: list[dict],
    new_message: str,
    image_base64: Optional[str] = None,
) -> dict:
    system_prompt = TIER_PROMPTS.get(tier, TIER_PROMPTS["stranger"]) + JSON_FORMAT_INSTRUCTION

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": _build_user_content(
                    user_name, memory_summary, recent_messages, new_message, image_base64
                ),
            },
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text}")
        data = resp.json()

    raw_text = data["choices"][0]["message"]["content"]
    cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)