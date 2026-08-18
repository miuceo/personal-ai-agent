                                                                                                                                                                                                                                                                                                                                                                                                                     main.py                                                                                                                                                                                                                                                                                                                                                                                                                                               
"""
main.py

Telethon-based personal secretary userbot. Logs into YOUR OWN account
(via phone number + API_ID/API_HASH) — no Telegram Business subscription
needed, no separate bot account.

Behavior:
- New incoming message in a private chat -> the bot waits 1 minute before
  doing anything, giving the owner a chance to jump in and reply personally
  first. If the owner hasn't replied by then, the bot answers.
- If the owner personally replies in a chat, the bot goes silent there for
  OWNER_PAUSE_MINUTES, then automatically resumes.
- If more than 24h pass since the last message in a chat, the short-term
  "live" context resets (but the long-term memory summary is kept).
- Every reply the bot sends on the owner's behalf is appended to a local
  unread-digest file. Only the owner (OWNER_ID) can retrieve it with
  /messages (sent to their own Saved Messages chat), or clear it with
  /read-all.
- Only text, photo, and voice messages are processed. Any other file type
  (documents, APK, EXE, ZIP, etc.) is completely ignored — never downloaded.

Run with: python main.py
"""

import asyncio
import base64

from telethon import TelegramClient, events
from telethon.sessions import StringSession

import db
import llm
import transcribe
import unread_store
from config import settings

client = TelegramClient(
    StringSession(settings.telegram_session), settings.api_id, settings.api_hash
)

INITIAL_REPLY_DELAY_SECONDS = settings.initial_reply_delay_seconds  # "kutish"

# Message IDs the bot itself just sent, so the outgoing-message handler
# doesn't mistake the bot's own reply for a manual reply typed by the owner.
SENT_BY_BOT: set[int] = set()


@client.on(events.NewMessage(outgoing=True))
async def handle_owner_outgoing(event: events.NewMessage.Event) -> None:
    """Tracks when the owner personally sends a message in a private chat."""
    if not event.is_private:
        return
    if event.message.id in SENT_BY_BOT:
        SENT_BY_BOT.discard(event.message.id)
        return

    me = await client.get_me()
    if event.chat_id == me.id:
        await handle_owner_command(event)
        return

    await db.ensure_chat(event.chat_id, "")
    await db.mark_owner_replied(event.chat_id)
    await db.append_recent_message(
        event.chat_id, "assistant", event.raw_text or "(media)", settings.short_history_limit
    )


async def handle_owner_command(event: events.NewMessage.Event) -> None:
    """Commands the owner sends to themself (Saved Messages) to control the bot."""
    text = (event.raw_text or "").strip()

    if text == "/messages":
        entries = unread_store.get_all()
        await event.reply(unread_store.format_digest(entries))

    elif text == "/read-all":
        count = unread_store.clear()
        await event.reply(f"{count} ta yozuv o'chirildi.")


@client.on(events.NewMessage(incoming=True))
async def handle_incoming(event: events.NewMessage.Event) -> None:
    if not event.is_private:
        return

    sender = await event.get_sender()
    if sender is None or getattr(sender, "bot", False):
        return

    # Never process anything from the owner's own other sessions here —
    # that's handled by handle_owner_outgoing above.
    if sender.id == settings.owner_id:
        return

    # Ignore any file that isn't a photo or a voice note — never download
    # documents, APKs, EXEs, ZIPs, etc.
    if event.document and not (event.photo or event.voice):
        return

    chat_id = event.chat_id
    user_name = getattr(sender, "first_name", None) or "Noma'lum"
    await db.ensure_chat(chat_id, user_name)

    # "1 daqiqa kutish" — give the owner a window to reply personally first.
    if not await db.owner_recently_active(chat_id, settings.owner_pause_minutes):
        await asyncio.sleep(INITIAL_REPLY_DELAY_SECONDS)

    # Re-check after the wait: the owner may have replied in the meantime,
    # either just now or already before this message arrived.
    if await db.owner_recently_active(chat_id, settings.owner_pause_minutes):
        if event.raw_text:
            await db.append_recent_message(chat_id, "user", event.raw_text, settings.short_history_limit)
        return

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
        user_name=user_name,
        memory_summary=memory["summary"],
        recent_messages=memory["recent_messages"],
        new_message=text,
        image_base64=image_b64,
    )

    reply_text = result["reply"]
    is_important = result.get("is_important", False)
    new_summary = result.get("memory_summary", memory["summary"])

    sent = await event.reply(reply_text)
    SENT_BY_BOT.add(sent.id)

    await db.append_recent_message(chat_id, "assistant", reply_text, settings.short_history_limit)
    await db.update_summary(chat_id, new_summary)
    await db.mark_bot_replied(chat_id)

    unread_store.append(
        user_name=user_name,
        their_message=text or "[rasm]",
        bot_reply=reply_text,
        is_important=is_important,
    )


async def main() -> None:
    await db.init_db()
    await client.start(phone=settings.phone_number)
    print("Secretary userbot ishga tushdi. To'xtatish uchun Ctrl+C.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())



