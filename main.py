"""
main.py

Telethon-based personal secretary userbot. Logs into YOUR OWN account
(via phone number + API_ID/API_HASH) — no Telegram Business subscription
needed, no separate bot account.

Behavior:
- New incoming message in a private chat -> the bot waits
  INITIAL_REPLY_DELAY_SECONDS before doing anything, giving the owner a
  chance to jump in and reply personally first. If the owner hasn't
  replied by then, the bot answers.
- If the owner personally replies in a chat, the bot goes silent there for
  OWNER_PAUSE_MINUTES, then automatically resumes.
- If more than 24h pass since the last message in a chat, the short-term
  "live" context resets (but the long-term memory summary is kept).
- Every reply the bot sends on the owner's behalf is recorded as an unread
  digest entry in Postgres. Only the owner (OWNER_ID) can retrieve it with
  /messages (sent to their own Saved Messages chat), or clear it with
  /read-all.
- Owner commands (sent to Saved Messages): /messages, /read-all, /pause
  (or /pause 30m, /pause 2h), /resume, /status.
- A message the model flags as `is_important` gets an immediate push to
  the owner's Saved Messages, in addition to the "band" auto-reply sent
  to the other person.
- Flood protection: auto-replies are capped per chat and globally within
  a rolling 1-hour window (MAX_REPLIES_PER_HOUR_PER_CHAT /
  MAX_REPLIES_PER_HOUR_GLOBAL).
- Only text, photo, and voice messages are processed. Any other file type
  (documents, APK, EXE, ZIP, etc.) is completely ignored — never downloaded.

Run with: python main.py
"""

import asyncio
import base64
import logging
import re
import time
from collections import defaultdict
from typing import Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession

import db
import llm
import transcribe
import unread_store
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("secretary")

client = TelegramClient(
    StringSession(settings.telegram_session), settings.api_id, settings.api_hash
)

INITIAL_REPLY_DELAY_SECONDS = settings.initial_reply_delay_seconds  # "kutish"

# Telegram hard-caps a single message at 4096 characters.
MAX_REPLY_CHARS = 4000

# Replies the bot is about to send, keyed by chat. Registered *before* the
# send call, because the outgoing-message update can reach us before
# `event.reply()` returns — otherwise the bot mistakes its own reply for a
# manual reply by the owner and mutes itself for OWNER_PAUSE_MINUTES.
PENDING_BOT_REPLIES: dict[int, list[str]] = {}

# Newest incoming message id per chat. If a newer message arrives while an
# older one is still inside its wait window, only the newest one replies —
# otherwise a burst of N messages produces N separate answers.
LAST_INCOMING_ID: dict[int, int] = {}

# Flood protection: timestamps (epoch seconds) of the bot's own replies in
# the last rolling hour, per chat and across all chats. Guards against a
# stuck loop or a message burst getting the account flagged by Telegram.
RATE_LIMIT_WINDOW_SECONDS = 3600
_chat_reply_times: dict[int, list[float]] = defaultdict(list)
_global_reply_times: list[float] = []

_PAUSE_DURATION_RE = re.compile(r"^(\d+)([mh])$", re.IGNORECASE)


def _prune_old(times: list[float]) -> None:
    cutoff = time.time() - RATE_LIMIT_WINDOW_SECONDS
    while times and times[0] < cutoff:
        times.pop(0)


def _is_rate_limited(chat_id: int) -> bool:
    _prune_old(_chat_reply_times[chat_id])
    _prune_old(_global_reply_times)
    if len(_chat_reply_times[chat_id]) >= settings.max_replies_per_hour_per_chat:
        return True
    if len(_global_reply_times) >= settings.max_replies_per_hour_global:
        return True
    return False


def _record_reply(chat_id: int) -> None:
    now = time.time()
    _chat_reply_times[chat_id].append(now)
    _global_reply_times.append(now)


def _parse_pause_duration(text: str) -> Optional[float]:
    """Parses '30m' / '2h' into seconds. None if the format is invalid."""
    match = _PAUSE_DURATION_RE.match(text.strip())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2).lower()
    return amount * (60 if unit == "m" else 3600)


async def is_bot_paused() -> bool:
    value = await db.get_state("paused_until")
    if not value:
        return False
    if value == "inf":
        return True
    try:
        return time.time() < float(value)
    except ValueError:
        return False


def _claim_pending_reply(chat_id: int, text: str) -> bool:
    """True if `text` is a reply this bot just sent in `chat_id` (consumes it)."""
    pending = PENDING_BOT_REPLIES.get(chat_id)
    if not pending or text not in pending:
        return False
    pending.remove(text)
    if not pending:
        PENDING_BOT_REPLIES.pop(chat_id, None)
    return True


async def _send_bot_reply(event: events.NewMessage.Event, chat_id: int, text: str) -> None:
    """Sends `text` as a reply, registering it so the echo isn't mistaken for
    the owner personally replying (see PENDING_BOT_REPLIES above)."""
    PENDING_BOT_REPLIES.setdefault(chat_id, []).append(text)
    try:
        await event.reply(text)
    except Exception:
        _claim_pending_reply(chat_id, text)
        raise


def _build_important_notification(user_name: str, sender, chat_id: int, message_text: str) -> str:
    username = getattr(sender, "username", None)
    link = f"https://t.me/{username}" if username else f"tg://user?id={chat_id}"
    preview = (message_text or "[rasm/ovozli xabar]").strip()
    if len(preview) > 300:
        preview = preview[:300] + "…"
    return f"🔴 MUHIM XABAR — {user_name}\nXabar: {preview}\nSuhbat: {link}"


@client.on(events.NewMessage(outgoing=True))
async def handle_owner_outgoing(event: events.NewMessage.Event) -> None:
    """Tracks when the owner personally sends a message in a private chat."""
    try:
        if not event.is_private:
            return

        if event.chat_id == settings.owner_id:
            await handle_owner_command(event)
            return

        if _claim_pending_reply(event.chat_id, event.raw_text or ""):
            return

        await db.ensure_chat(event.chat_id, "")
        await db.mark_owner_replied(event.chat_id)
        await db.append_recent_message(
            event.chat_id,
            "assistant",
            event.raw_text or "(media)",
            settings.short_history_limit,
        )
    except Exception:
        log.exception("Failed to handle outgoing message in chat %s", event.chat_id)


async def handle_owner_command(event: events.NewMessage.Event) -> None:
    """Commands the owner sends to themself (Saved Messages) to control the bot."""
    text = (event.raw_text or "").strip()

    if text == "/messages":
        entries = await db.get_unread_entries()
        await event.reply(unread_store.format_digest(entries))

    elif text == "/read-all":
        count = await db.clear_unread_entries()
        await event.reply(f"{count} ta yozuv o'chirildi.")

    elif text == "/pause":
        await db.set_state("paused_until", "inf")
        await event.reply(
            "⏸ Bot butunlay to'xtatildi — hech kimga avtomatik javob bermaydi. "
            "Davom ettirish uchun /resume yozing."
        )

    elif text.startswith("/pause "):
        duration_text = text[len("/pause ") :].strip()
        seconds = _parse_pause_duration(duration_text)
        if seconds is None:
            await event.reply(
                "Noto'g'ri format. Masalan: /pause 30m yoki /pause 2h"
            )
        else:
            await db.set_state("paused_until", str(time.time() + seconds))
            await event.reply(f"⏸ Bot {duration_text} davomida to'xtatildi.")

    elif text == "/resume":
        await db.delete_state("paused_until")
        await event.reply("▶️ Bot davom etmoqda.")

    elif text == "/status":
        paused_until = await db.get_state("paused_until")
        if not paused_until:
            status_line = "▶️ Faol — avtomatik javob berilmoqda."
        elif paused_until == "inf":
            status_line = "⏸ To'xtatilgan (muddatsiz)."
        else:
            remaining_min = max(0, int((float(paused_until) - time.time()) / 60))
            status_line = f"⏸ To'xtatilgan — yana {remaining_min} daqiqadan davom etadi."

        unread_count = len(await db.get_unread_entries())
        _prune_old(_global_reply_times)
        await event.reply(
            f"{status_line}\n"
            f"O'qilmagan yozuvlar: {unread_count} ta.\n"
            f"Bu soatda javoblar: {len(_global_reply_times)}/{settings.max_replies_per_hour_global}."
        )


@client.on(events.NewMessage(incoming=True))
async def handle_incoming(event: events.NewMessage.Event) -> None:
    try:
        await _handle_incoming(event)
    except Exception:
        log.exception("Failed to handle incoming message in chat %s", event.chat_id)


async def _handle_incoming(event: events.NewMessage.Event) -> None:
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
    if event.media is not None and not (event.photo or event.voice):
        return

    chat_id = event.chat_id
    message_id = event.message.id
    user_name = getattr(sender, "first_name", None) or "Noma'lum"
    await db.ensure_chat(chat_id, user_name)

    LAST_INCOMING_ID[chat_id] = message_id

    # Owner globally paused the bot (via /pause) — stay out of every chat,
    # but keep recording context for continuity once resumed.
    if await is_bot_paused():
        if event.raw_text:
            await db.append_recent_message(
                chat_id, "user", event.raw_text, settings.short_history_limit
            )
        return

    # Give the owner a window to reply personally first.
    if not await db.owner_recently_active(chat_id, settings.owner_pause_minutes):
        await asyncio.sleep(INITIAL_REPLY_DELAY_SECONDS)

    # Re-check after the wait: the owner may have replied in the meantime,
    # or a newer message from the same person may have superseded this one.
    superseded = LAST_INCOMING_ID.get(chat_id) != message_id
    if superseded or await db.owner_recently_active(chat_id, settings.owner_pause_minutes):
        if event.raw_text:
            await db.append_recent_message(
                chat_id, "user", event.raw_text, settings.short_history_limit
            )
        return

    # Flood protection: too many auto-replies already sent this hour —
    # stay quiet rather than risk the account getting flagged.
    if _is_rate_limited(chat_id):
        log.warning("Rate limit hit for chat %s; skipping auto-reply", chat_id)
        if event.raw_text:
            await db.append_recent_message(
                chat_id, "user", event.raw_text, settings.short_history_limit
            )
        return

    text = event.raw_text or ""
    image_b64 = None

    if event.photo:
        photo_bytes = await event.download_media(bytes)
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
    elif event.voice:
        voice_bytes = await event.download_media(bytes)
        try:
            text = await transcribe.transcribe_voice(voice_bytes)
        except Exception:
            log.exception("Voice transcription failed for chat %s", chat_id)
            try:
                await _send_bot_reply(
                    event,
                    chat_id,
                    "Ovozli xabaringizni tushunolmadim — texnik xatolik yuz berdi. "
                    "Iltimos, matn bilan yozib yuboring.",
                )
            except Exception:
                log.exception("Failed to send transcription-failure reply in chat %s", chat_id)
            return

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

    reply_text = str(result.get("reply") or "").strip()[:MAX_REPLY_CHARS]
    if not reply_text:
        log.warning("Model returned an empty reply for chat %s; skipping", chat_id)
        return

    is_important = bool(result.get("is_important", False))
    new_summary = result.get("memory_summary") or memory["summary"]

    if is_important:
        try:
            await client.send_message(
                settings.owner_id,
                _build_important_notification(user_name, sender, chat_id, text),
            )
        except Exception:
            log.exception("Failed to send importance notification for chat %s", chat_id)

    await _send_bot_reply(event, chat_id, reply_text)
    _record_reply(chat_id)

    await db.append_recent_message(chat_id, "assistant", reply_text, settings.short_history_limit)
    await db.update_summary(chat_id, new_summary)
    await db.mark_bot_replied(chat_id)

    await db.add_unread_entry(
        user_name=user_name,
        their_message=text or "[rasm]",
        bot_reply=reply_text,
        is_important=is_important,
    )


async def main() -> None:
    await db.init_db()
    await client.start(phone=settings.phone_number)
    log.info("Secretary userbot ishga tushdi. To'xtatish uchun Ctrl+C.")
    try:
        await client.run_until_disconnected()
    finally:
        await db.close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("To'xtatildi.")
