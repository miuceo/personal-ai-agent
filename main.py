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
- Owner commands (sent to Saved Messages): /pause (or /pause 30m, /pause 2h),
  /resume, /status, /inbox (or /unread), /read <id>, /delete <id>, /readall.
  Plain-language equivalents of the inbox commands also work (e.g.
  "o'qilmagan xabarlarni ko'rsat", "42-ni o'chir") — see
  _try_natural_language_inbox_command.
- A message the model flags as `is_important` gets an immediate push to
  the owner's Saved Messages, in addition to the "band" auto-reply sent
  to the other person. Every incoming message (important or not) is also
  recorded in the inbox table for later review/mark-read/delete — via
  /inbox, the inline buttons on each listed item, or natural language.
  Access is inherently owner-only (Saved Messages and button callbacks on
  the owner's own account aren't reachable by anyone else).
- Flood protection: auto-replies are capped per chat and globally within
  a rolling 1-hour window (MAX_REPLIES_PER_HOUR_PER_CHAT /
  MAX_REPLIES_PER_HOUR_GLOBAL). The slot is reserved before the LLM call
  starts (not after the reply is sent) so a burst of messages can't all
  slip past the check while earlier ones are still mid-flight.
- Only text, photo, and voice messages are processed. Any other file type
  (documents, APK, EXE, ZIP, etc.) gets an explicit "can't open this" reply
  instead — nothing outside photo/voice is ever downloaded.

Run with: python main.py
"""

import asyncio
import base64
import logging
import re
import time
from collections import defaultdict
from typing import Optional

from telethon import Button, TelegramClient, events
from telethon.sessions import StringSession

import db
import llm
import transcribe
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

# Sent immediately (no AI, no initial-reply delay) for any incoming file
# that isn't a Telegram photo or voice note — documents, videos, stickers,
# APK/EXE/ZIP, a PNG sent as a file instead of a compressed photo, etc.
# Nothing outside photo/voice is ever downloaded or opened; this makes that
# explicit to the sender instead of leaving them wondering why the bot went
# silent.
UNSUPPORTED_MEDIA_REPLY = (
    "Kechirasiz, bu turdagi faylni ocholmayman — menda bunga ruxsat yo'q. "
    "Faqat rasm (JPEG/PNG) va Telegram orqali yuborilgan ovozli xabarlarni "
    "qabul qilaman."
)

# Replies the bot is about to send, keyed by chat, as (text, sent_at) pairs.
# Registered *before* the send call, because the outgoing-message update can
# reach us before `event.reply()` returns — otherwise the bot mistakes its
# own reply for a manual reply by the owner and mutes itself for
# OWNER_PAUSE_MINUTES. Entries older than PENDING_REPLY_TTL_SECONDS are
# ignored (and swept up on the next check for that chat) so that a lost/
# delayed echo can't permanently block a later genuine owner message that
# happens to repeat the same text.
PENDING_REPLY_TTL_SECONDS = 60
PENDING_BOT_REPLIES: dict[int, list[tuple[str, float]]] = {}

# Newest incoming message id per chat. If a newer message arrives while an
# older one is still inside its wait window, only the newest one replies —
# otherwise a burst of N messages produces N separate answers.
LAST_INCOMING_ID: dict[int, int] = {}

# Last time we saw any activity (incoming message) for a chat. Used only to
# garbage-collect the in-memory dicts above for chats that have gone quiet —
# without this, LAST_INCOMING_ID/_chat_reply_times/PENDING_BOT_REPLIES and
# db's per-chat locks would all grow for as long as the process runs.
_chat_last_activity: dict[int, float] = {}
CHAT_IDLE_TTL_SECONDS = 48 * 60 * 60  # 2x the 24h "live context" window
CLEANUP_INTERVAL_SECONDS = 30 * 60

# Flood protection: timestamps (epoch seconds) of the bot's own replies in
# the last rolling hour, per chat and across all chats. Guards against a
# stuck loop or a message burst getting the account flagged by Telegram.
RATE_LIMIT_WINDOW_SECONDS = 3600
_chat_reply_times: dict[int, list[float]] = defaultdict(list)
_global_reply_times: list[float] = []

# Cached mirror of bot_state["paused_until"] so the hot path doesn't hit the
# DB on every single incoming message just to check whether we're paused —
# this value only ever changes via the owner's /pause and /resume commands,
# which update the cache themselves right after writing to the DB.
_paused_until_cache: Optional[str] = None

_PAUSE_DURATION_RE = re.compile(r"^(\d+)([mh])$", re.IGNORECASE)


def _prune_old(times: list[float]) -> None:
    cutoff = time.time() - RATE_LIMIT_WINDOW_SECONDS
    while times and times[0] < cutoff:
        times.pop(0)


def _try_reserve_reply_slot(chat_id: int) -> bool:
    """Atomically checks-and-reserves a flood-limit slot. Reserving *before*
    the (slow) LLM call starts — rather than recording only after a reply is
    actually sent — is what prevents a burst of near-simultaneous messages
    from all passing the check while earlier ones are still in flight."""
    _prune_old(_chat_reply_times[chat_id])
    _prune_old(_global_reply_times)
    if len(_chat_reply_times[chat_id]) >= settings.max_replies_per_hour_per_chat:
        return False
    if len(_global_reply_times) >= settings.max_replies_per_hour_global:
        return False
    now = time.time()
    _chat_reply_times[chat_id].append(now)
    _global_reply_times.append(now)
    return True


def _release_reply_slot(chat_id: int) -> None:
    """Gives back a slot reserved by _try_reserve_reply_slot when it turns
    out no reply was actually sent (empty LLM result, send failure, etc.)."""
    if _chat_reply_times[chat_id]:
        _chat_reply_times[chat_id].pop()
    if _global_reply_times:
        _global_reply_times.pop()


def _parse_pause_duration(text: str) -> Optional[float]:
    """Parses '30m' / '2h' into seconds. None if the format is invalid."""
    match = _PAUSE_DURATION_RE.match(text.strip())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2).lower()
    return amount * (60 if unit == "m" else 3600)


def is_bot_paused() -> bool:
    value = _paused_until_cache
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
    if not pending:
        return False

    now = time.time()
    fresh = [(t, ts) for t, ts in pending if now - ts < PENDING_REPLY_TTL_SECONDS]
    matched = False
    for i, (t, _ts) in enumerate(fresh):
        if t == text:
            fresh.pop(i)
            matched = True
            break

    if fresh:
        PENDING_BOT_REPLIES[chat_id] = fresh
    else:
        PENDING_BOT_REPLIES.pop(chat_id, None)
    return matched


async def _send_bot_reply(event: events.NewMessage.Event, chat_id: int, text: str) -> None:
    """Sends `text` as a reply, registering it so the echo isn't mistaken for
    the owner personally replying (see PENDING_BOT_REPLIES above)."""
    PENDING_BOT_REPLIES.setdefault(chat_id, []).append((text, time.time()))
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


# --- Inbox: every incoming message is recorded here (regardless of whether
# the AI auto-replied to it) so the owner can review, mark read, or delete
# them later — via /inbox, inline buttons, or plain-language requests in
# Saved Messages. Access is inherently owner-only: Saved Messages and
# button callbacks on the owner's own account are not reachable by anyone
# else, and handle_callback double-checks the sender id regardless. ---

INBOX_PAGE_SIZE = 10


async def _record_inbox(
    chat_id: int, user_name: str, message_text: str, is_important: bool, bot_reply: Optional[str]
) -> None:
    try:
        await db.add_inbox_message(chat_id, user_name, message_text, is_important, bot_reply)
    except Exception:
        log.exception("Failed to record inbox message for chat %s", chat_id)


def _inbox_buttons(message_id: int) -> list:
    return [[
        Button.inline("✅ O'qildi", data=f"read:{message_id}"),
        Button.inline("🗑 O'chirish", data=f"delete:{message_id}"),
    ]]


async def _send_inbox_list(event: events.NewMessage.Event) -> None:
    rows = await db.list_unread_inbox(INBOX_PAGE_SIZE)
    total_unread = await db.count_unread_inbox()

    if not rows:
        await event.reply("O'qilmagan xabar yo'q.")
        return

    await event.reply(f"O'qilmagan xabarlar: {total_unread} ta. Oxirgi {len(rows)} tasi:")
    for row in rows:
        preview = (row["message_text"] or "(matn yo'q)").strip()
        if len(preview) > 500:
            preview = preview[:500] + "…"
        important_mark = " 🔴" if row["is_important"] else ""
        header = f"#{row['id']} — {row['user_name'] or 'Nomaʼlum'} ({row['created_at']:%Y-%m-%d %H:%M})"
        await event.reply(f"{header}{important_mark}\n{preview}", buttons=_inbox_buttons(row["id"]))


# Best-effort keyword matching for the owner's plain-language inbox
# requests in Saved Messages (e.g. "o'qilmagan xabarlarni ko'rsat",
# "42-ni o'chir"). Deliberately NOT LLM-based: these can trigger a
# destructive action (delete), so behavior needs to be deterministic and
# predictable rather than inferred by a model that could misread intent.
_APOSTROPHES = str.maketrans("", "", "'’ʻʼ`")
_NL_NUMBER_RE = re.compile(r"\d+")


def _normalize_uz(text: str) -> str:
    return text.lower().translate(_APOSTROPHES)


async def _try_natural_language_inbox_command(event: events.NewMessage.Event, text: str) -> bool:
    normalized = _normalize_uz(text)
    number_match = _NL_NUMBER_RE.search(normalized)

    if re.search(r"oqilmagan|inbox|yangi xabar", normalized) and not number_match:
        await _send_inbox_list(event)
        return True

    if re.search(r"(hammasini|barchasini).{0,10}oqi", normalized):
        n = await db.mark_all_inbox_read()
        await event.reply(f"{n} ta xabar o'qildi deb belgilandi.")
        return True

    if "ochir" in normalized and number_match:
        message_id = int(number_match.group())
        ok = await db.delete_inbox_message(message_id)
        await event.reply("O'chirildi." if ok else f"#{message_id} topilmadi.")
        return True

    if "oqi" in normalized and number_match:
        message_id = int(number_match.group())
        ok = await db.mark_inbox_read(message_id)
        await event.reply("O'qildi deb belgilandi." if ok else f"#{message_id} topilmadi.")
        return True

    return False


@client.on(events.CallbackQuery)
async def handle_callback(event: events.CallbackQuery.Event) -> None:
    try:
        if event.sender_id != settings.owner_id:
            await event.answer("Ruxsat yo'q.", alert=True)
            return

        action, _, id_text = event.data.decode().partition(":")
        try:
            message_id = int(id_text)
        except ValueError:
            await event.answer("Xato so'rov.")
            return

        if action == "read":
            ok = await db.mark_inbox_read(message_id)
            await event.answer("O'qildi deb belgilandi." if ok else "Topilmadi (o'chirilgan bo'lishi mumkin).")
            if ok:
                await event.edit(buttons=None)
        elif action == "delete":
            ok = await db.delete_inbox_message(message_id)
            await event.answer("O'chirildi." if ok else "Topilmadi.")
            if ok:
                await event.delete()
    except Exception:
        log.exception("Failed to handle inbox callback")


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
    global _paused_until_cache
    text = (event.raw_text or "").strip()

    if text == "/pause":
        await db.set_state("paused_until", "inf")
        _paused_until_cache = "inf"
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
            new_value = str(time.time() + seconds)
            await db.set_state("paused_until", new_value)
            _paused_until_cache = new_value
            await event.reply(f"⏸ Bot {duration_text} davomida to'xtatildi.")

    elif text == "/resume":
        await db.delete_state("paused_until")
        _paused_until_cache = None
        await event.reply("▶️ Bot davom etmoqda.")

    elif text == "/status":
        paused_until = _paused_until_cache
        if not paused_until:
            status_line = "▶️ Faol — avtomatik javob berilmoqda."
        elif paused_until == "inf":
            status_line = "⏸ To'xtatilgan (muddatsiz)."
        else:
            remaining_min = max(0, int((float(paused_until) - time.time()) / 60))
            status_line = f"⏸ To'xtatilgan — yana {remaining_min} daqiqadan davom etadi."

        _prune_old(_global_reply_times)
        await event.reply(
            f"{status_line}\n"
            f"Bu soatda javoblar: {len(_global_reply_times)}/{settings.max_replies_per_hour_global}."
        )

    elif text in ("/inbox", "/unread"):
        await _send_inbox_list(event)

    elif text == "/readall":
        n = await db.mark_all_inbox_read()
        await event.reply(f"{n} ta xabar o'qildi deb belgilandi.")

    elif text.startswith("/read "):
        id_text = text[len("/read ") :].strip()
        if id_text.isdigit():
            ok = await db.mark_inbox_read(int(id_text))
            await event.reply("O'qildi deb belgilandi." if ok else f"#{id_text} topilmadi.")
        else:
            await event.reply("Noto'g'ri format. Masalan: /read 42")

    elif text.startswith("/delete "):
        id_text = text[len("/delete ") :].strip()
        if id_text.isdigit():
            ok = await db.delete_inbox_message(int(id_text))
            await event.reply("O'chirildi." if ok else f"#{id_text} topilmadi.")
        else:
            await event.reply("Noto'g'ri format. Masalan: /delete 42")

    elif not text.startswith("/"):
        # Plain-language inbox requests ("o'qilmagan xabarlarni ko'rsat",
        # "42-ni o'chir", ...). Anything unrecognized is left alone — Saved
        # Messages doubles as the owner's personal notes, so silently
        # ignoring unrelated text (as before) is the right default.
        await _try_natural_language_inbox_command(event, text)


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

    chat_id = event.chat_id
    message_id = event.message.id
    user_name = getattr(sender, "first_name", None) or "Noma'lum"
    await db.ensure_chat(chat_id, user_name)

    LAST_INCOMING_ID[chat_id] = message_id
    _chat_last_activity[chat_id] = time.time()

    # Owner globally paused the bot (via /pause) — stay out of every chat,
    # but keep recording context for continuity once resumed.
    if is_bot_paused():
        if event.raw_text:
            await db.append_recent_message(
                chat_id, "user", event.raw_text, settings.short_history_limit
            )
            await _record_inbox(chat_id, user_name, event.raw_text, False, None)
        return

    # Never download or open any file that isn't a photo or a voice note —
    # documents, APKs, EXEs, ZIPs, videos, stickers, an image sent as a
    # document instead of a compressed photo, etc. Reply immediately (no AI
    # involved, no initial-reply wait — this is a fixed capability notice,
    # not a judgment call) so the sender knows why nothing happened, rather
    # than silently going nowhere.
    if event.media is not None and not (event.photo or event.voice):
        if _try_reserve_reply_slot(chat_id):
            try:
                await _send_bot_reply(event, chat_id, UNSUPPORTED_MEDIA_REPLY)
                await _record_inbox(
                    chat_id, user_name, "[qo'llab-quvvatlanmaydigan fayl]", False, UNSUPPORTED_MEDIA_REPLY
                )
            except Exception:
                log.exception("Failed to send unsupported-media reply in chat %s", chat_id)
        return

    # Give the owner a window to reply personally first.
    memory = await db.get_memory(chat_id)
    if db.owner_active_in(memory, settings.owner_pause_minutes):
        if event.raw_text:
            await db.append_recent_message(
                chat_id, "user", event.raw_text, settings.short_history_limit
            )
            await _record_inbox(chat_id, user_name, event.raw_text, False, None)
        return
    await asyncio.sleep(INITIAL_REPLY_DELAY_SECONDS)

    # Re-check after the wait: a newer message from the same person may have
    # superseded this one, or the owner may have replied in the meantime —
    # state may have changed during the sleep, so this re-read (unlike the
    # one above) can't be skipped or cached across the wait.
    superseded = LAST_INCOMING_ID.get(chat_id) != message_id
    if superseded:
        if event.raw_text:
            await db.append_recent_message(
                chat_id, "user", event.raw_text, settings.short_history_limit
            )
            await _record_inbox(chat_id, user_name, event.raw_text, False, None)
        return

    memory = await db.get_memory(chat_id)
    if db.owner_active_in(memory, settings.owner_pause_minutes):
        if event.raw_text:
            await db.append_recent_message(
                chat_id, "user", event.raw_text, settings.short_history_limit
            )
            await _record_inbox(chat_id, user_name, event.raw_text, False, None)
        return

    # Flood protection: reserve a slot now, before the slow LLM call, so a
    # burst of messages can't all pass the check while earlier ones are
    # still in flight. Released below on any path that ends up not sending
    # an actual reply.
    if not _try_reserve_reply_slot(chat_id):
        log.warning("Rate limit hit for chat %s; skipping auto-reply", chat_id)
        if event.raw_text:
            await db.append_recent_message(
                chat_id, "user", event.raw_text, settings.short_history_limit
            )
            await _record_inbox(chat_id, user_name, event.raw_text, False, None)
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
            apology = (
                "Ovozli xabaringizni tushunolmadim — texnik xatolik yuz berdi. "
                "Iltimos, matn bilan yozib yuboring."
            )
            try:
                await _send_bot_reply(event, chat_id, apology)
                await _record_inbox(chat_id, user_name, "[ovozli xabar — transkripsiya xatosi]", False, apology)
            except Exception:
                log.exception("Failed to send transcription-failure reply in chat %s", chat_id)
            return

    if not text.strip() and image_b64 is None:
        _release_reply_slot(chat_id)
        return

    # Records the user's turn and hands back the resulting memory in one
    # round-trip, so the LLM call below doesn't need a separate read.
    memory = await db.append_recent_message(chat_id, "user", text or "(rasm)", settings.short_history_limit)

    result = await llm.generate_reply(
        user_name=user_name,
        memory_summary=memory["summary"],
        recent_messages=memory["recent_messages"],
        new_message=text,
        image_base64=image_b64,
    )

    reply_text = str(result.get("reply") or "").strip()[:MAX_REPLY_CHARS]
    if not reply_text:
        _release_reply_slot(chat_id)
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
    await _record_inbox(chat_id, user_name, text or "(rasm)", is_important, reply_text)

    # Single read-modify-write for the assistant turn + summary + timestamp,
    # replacing what used to be three separate DB round-trips.
    await db.record_bot_reply(chat_id, reply_text, new_summary, settings.short_history_limit)


def _cleanup_in_memory_state() -> None:
    """Drops in-memory bookkeeping for chats that have gone quiet. Without
    this, LAST_INCOMING_ID / _chat_last_activity / PENDING_BOT_REPLIES /
    per-chat locks (in db.py) would all grow for as long as the process
    stays up — this is meant to run every process for months at a time."""
    now = time.time()

    # _chat_reply_times: drop entries that pruned down to empty, regardless
    # of chat idle time — no point keeping an empty list around.
    empty_reply_chats = [cid for cid, times in _chat_reply_times.items() if not times]
    for cid in empty_reply_chats:
        _chat_reply_times.pop(cid, None)

    # PENDING_BOT_REPLIES: drop fully-expired entries.
    for cid in list(PENDING_BOT_REPLIES.keys()):
        fresh = [(t, ts) for t, ts in PENDING_BOT_REPLIES[cid] if now - ts < PENDING_REPLY_TTL_SECONDS]
        if fresh:
            PENDING_BOT_REPLIES[cid] = fresh
        else:
            PENDING_BOT_REPLIES.pop(cid, None)

    # Chats idle for longer than CHAT_IDLE_TTL_SECONDS: drop their tracking
    # entries entirely, including the per-chat DB lock (only if not
    # currently held).
    idle_chats = [
        cid for cid, last in _chat_last_activity.items() if now - last > CHAT_IDLE_TTL_SECONDS
    ]
    for cid in idle_chats:
        _chat_last_activity.pop(cid, None)
        LAST_INCOMING_ID.pop(cid, None)
        _chat_reply_times.pop(cid, None)
        PENDING_BOT_REPLIES.pop(cid, None)
    db.drop_idle_locks(idle_chats)

    if idle_chats or empty_reply_chats:
        log.info(
            "Cleanup: dropped %d idle chat(s), %d empty reply-time entr(y/ies)",
            len(idle_chats),
            len(empty_reply_chats),
        )


async def _periodic_cleanup() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            _cleanup_in_memory_state()
        except Exception:
            log.exception("Periodic in-memory cleanup failed")


async def main() -> None:
    global _paused_until_cache
    await db.init_db()
    _paused_until_cache = await db.get_state("paused_until")

    await client.start(phone=settings.phone_number)
    log.info("Secretary userbot ishga tushdi. To'xtatish uchun Ctrl+C.")

    cleanup_task = asyncio.create_task(_periodic_cleanup())
    try:
        await client.run_until_disconnected()
    finally:
        cleanup_task.cancel()
        await db.close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("To'xtatildi.")
