"""
main.py

Telethon-based personal secretary userbot (logs into your own account,
no Telegram Business subscription needed).

Features in this version:
- Text, photo, and voice message understanding.
- Three response tiers: owner / known_contact / stranger.
- Persistent JSON memory per chat, stored in Neon PostgreSQL (db.py).
- Live activity log: every reply the bot sends is also echoed to your own
  "Saved Messages" chat in real time, so you always know what it said,
  without having to ask.
- If you personally reply in a chat, the bot pauses there for
  OWNER_PAUSE_MINUTES, then resumes automatically.

Run with: python main.py
"""

import asyncio
import base64
import io

from telethon import TelegramClient, events

import db
import llm
import transcribe
from config import settings

client = TelegramClient("secretary_session", settings.api_id, settings.api_hash)

# Message IDs the bot itself just sent — lets the outgoing-message handler
# tell "the bot's own reply" apart from "the owner typed something manually".
SENT_BY_BOT: set[int] = set()


async def log_to_saved_messages(text: str) -> None:
    """Live-logs bot activity to the owner's own Saved Messages chat."""
    me = await client.get_me()
    sent = await client.send_message(me.id, text)
    SENT_BY_BOT.add(sent.id)


@client.on(events.NewMessage(incoming=True, outgoing=True))
async def handle_message(event: events.NewMessage.Event) -> None:
    if not event.is_private:
        return

    chat_id = event.chat_id
    sender = await event.get_sender()
    user_name = getattr(sender, "first_name", None) or "Noma'lum"

    # --- Case 1: message sent by the owner (from any device, including this script) ---
    if event.out:
        if event.message.id in SENT_BY_BOT:
            SENT_BY_BOT.discard(event.message.id)
            return
        await db.ensure_chat(chat_id, user_name)
        await db.mark_owner_replied(chat_id)
        await db.append_recent_message(
            chat_id, "assistant", event.raw_text or "(media)", settings.short_history_limit
        )
        return

    # --- Case 2: incoming message from someone else ---
    me = await client.get_me()
    if chat_id == me.id:
        return  # ignore messages in Saved Messages itself — that's the log channel

    is_owner = sender.id == settings.owner_id
    if is_owner:
        # The owner messaging the bot from a different account/session — treat as a command
        # channel too, but this build doesn't define owner commands here beyond logging.
        return

    already_known = await db.is_known_contact(chat_id)
    tier = "known_contact" if already_known else "stranger"

    await db.ensure_chat(chat_id, user_name)

    if await db.owner_recently_active(chat_id, settings.owner_pause_minutes):
        if event.raw_text:
            await db.append_recent_message(chat_id, "user", event.raw_text, settings.short_history_limit)
        return  # owner is handling this chat personally right now — stay quiet

    text = event.raw_text or ""
    image_b64 = None

    if event.photo:
        photo_bytes = await event.download_media(bytes)
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
    elif event.voice:
        voice_bytes = await event.download_media(bytes)
        text = await transcribe.transcribe_voice(voice_bytes)

    if not text.strip() and image_b64 is None:
        return

    await db.append_recent_message(chat_id, "user", text or "(rasm)", settings.short_history_limit)

    memory = await db.get_memory(chat_id)
    result = await llm.generate_reply(
        tier=tier,
        user_name=user_name,
        memory_summary=memory["summary"],
        recent_messages=memory["recent_messages"],
        new_message=text,
        image_base64=image_b64,
    )

    reply_text = result["reply"]
    new_summary = result.get("memory_summary", memory["summary"])

    sent = await event.reply(reply_text)
    SENT_BY_BOT.add(sent.id)

    await db.append_recent_message(chat_id, "assistant", reply_text, settings.short_history_limit)
    await db.update_summary(chat_id, new_summary)
    await db.mark_bot_replied(chat_id)

    tier_label = "🆕 Yangi odam" if tier == "stranger" else "👤 Tanish"
    await log_to_saved_messages(
        f"{tier_label}: {user_name}\n"
        f"Ular: {text or '[rasm]'}\n"
        f"Men javob berdim: {reply_text}"
    )


async def main() -> None:
    await db.init_db()
    await client.start(phone=settings.phone_number)
    print("Secretary userbot ishga tushdi. To'xtatish uchun Ctrl+C.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())