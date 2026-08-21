"""
db.py

Persistent memory backed by Neon PostgreSQL, using a single JSONB column
per chat — functions here read/write/delete fields inside that JSON blob
the same way you would with a local JSON file, but the data survives
redeploys and restarts.

Memory JSON shape (per chat_id):
{
    "summary": str,                         # long-term facts, kept forever
    "recent_messages": [...],               # short-term "live" context
    "last_message_at": float | None,        # any message (in or out)
    "last_owner_reply_at": float | None,     # owner personally replied
    "last_bot_reply_at": float | None,
}

24-hour rule: if more than 24h passed since the last message in a chat,
`recent_messages` is cleared (fresh short-term context) but `summary` is
kept — long-term facts about who this person is are not forgotten.
"""

import asyncio
import json
import time
from collections import defaultdict
from typing import Any, Optional

import asyncpg

from config import settings

_pool: Optional[asyncpg.Pool] = None

# Every memory update is a read-modify-write of one JSON blob, so two
# concurrent handlers touching the same chat would clobber each other.
# One lock per chat serializes them. Never pruned as chats come and go, so
# callers should periodically drop_idle_locks() for chats gone quiet —
# otherwise this dict grows for as long as the process runs.
_chat_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

RECENT_CONTEXT_TTL_SECONDS = 24 * 60 * 60

# The prompt asks the model to keep memory_summary under ~400 words, but
# nothing enforces that on the model's side — left unchecked it drifts
# longer every turn (and gets re-sent to the LLM on every single message,
# so an unbounded summary means slowly growing latency/cost). Truncated
# here so every write path gets the cap regardless of caller.
MAX_SUMMARY_CHARS = 3000

EMPTY_MEMORY = {
    "summary": "",
    "recent_messages": [],
    "last_message_at": None,
    "last_owner_reply_at": None,
    "last_bot_reply_at": None,
}


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                chat_id BIGINT PRIMARY KEY,
                user_name TEXT,
                tier TEXT NOT NULL DEFAULT 'stranger',
                memory JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inbox_messages (
                id BIGSERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_name TEXT,
                message_text TEXT,
                is_important BOOLEAN NOT NULL DEFAULT FALSE,
                bot_reply TEXT,
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS inbox_messages_unread_idx "
            "ON inbox_messages (created_at) WHERE is_read = FALSE"
        )


def _pool_or_raise() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized — call init_db() first.")
    return _pool


async def is_known_contact(chat_id: int) -> bool:
    """True if we've exchanged messages with this chat before."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("SELECT 1 FROM chats WHERE chat_id = $1", chat_id)
    return row is not None


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_memory(chat_id: int) -> dict[str, Any]:
    pool = _pool_or_raise()
    row = await pool.fetchrow("SELECT memory FROM chats WHERE chat_id = $1", chat_id)
    if row is None:
        return _empty_memory()
    memory = json.loads(row["memory"])
    # A row inserted before a field existed (or an empty '{}' default) must
    # not KeyError downstream.
    for key, value in EMPTY_MEMORY.items():
        memory.setdefault(key, value.copy() if isinstance(value, list) else value)
    return memory


def _empty_memory() -> dict[str, Any]:
    return {
        key: (value.copy() if isinstance(value, list) else value)
        for key, value in EMPTY_MEMORY.items()
    }


async def ensure_chat(chat_id: int, user_name: str) -> None:
    pool = _pool_or_raise()
    await pool.execute(
        """
        INSERT INTO chats (chat_id, user_name, memory, updated_at)
        VALUES ($1, $2, $3::jsonb, now())
        ON CONFLICT (chat_id) DO UPDATE
            SET user_name = COALESCE(NULLIF(EXCLUDED.user_name, ''), chats.user_name)
        """,
        chat_id,
        user_name,
        json.dumps(EMPTY_MEMORY),
    )


async def save_memory(chat_id: int, memory: dict[str, Any]) -> None:
    """Overwrite the full JSON memory blob for a chat (like rewriting a JSON file)."""
    pool = _pool_or_raise()
    await pool.execute(
        "UPDATE chats SET memory = $2::jsonb, updated_at = now() WHERE chat_id = $1",
        chat_id,
        json.dumps(memory),
    )


def _append_message(memory: dict[str, Any], role: str, text: str, limit: int) -> None:
    """Mutates `memory` in place: applies the 24h rule, appends the message,
    trims to `limit`. Shared by the read-modify-write helpers below so the
    24h-reset logic lives in exactly one place."""
    last_at = memory.get("last_message_at")
    if last_at and (time.time() - last_at) > RECENT_CONTEXT_TTL_SECONDS:
        memory["recent_messages"] = []

    memory["recent_messages"].append({"role": role, "text": text, "ts": time.time()})
    memory["recent_messages"] = memory["recent_messages"][-max(limit, 1) :]
    memory["last_message_at"] = time.time()


async def append_recent_message(chat_id: int, role: str, text: str, limit: int) -> dict[str, Any]:
    """Appends one message and returns the resulting memory, so callers that
    need the memory right after (e.g. to build the LLM prompt) don't have to
    issue a separate get_memory() read-trip."""
    async with _chat_locks[chat_id]:
        memory = await get_memory(chat_id)
        _append_message(memory, role, text, limit)
        await save_memory(chat_id, memory)
        return memory


async def record_bot_reply(chat_id: int, reply_text: str, new_summary: str, limit: int) -> None:
    """Single read-modify-write for everything that changes once the bot has
    sent its reply: appends the assistant turn, updates the summary (capped
    at MAX_SUMMARY_CHARS), and marks last_bot_reply_at — replacing what used
    to be three separate read+write round-trips."""
    async with _chat_locks[chat_id]:
        memory = await get_memory(chat_id)
        _append_message(memory, "assistant", reply_text, limit)
        memory["summary"] = (new_summary or memory["summary"])[:MAX_SUMMARY_CHARS]
        memory["last_bot_reply_at"] = time.time()
        await save_memory(chat_id, memory)


async def _set_field(chat_id: int, key: str, value: Any) -> None:
    async with _chat_locks[chat_id]:
        memory = await get_memory(chat_id)
        memory[key] = value
        await save_memory(chat_id, memory)


async def update_summary(chat_id: int, new_summary: str) -> None:
    await _set_field(chat_id, "summary", new_summary[:MAX_SUMMARY_CHARS])


async def mark_owner_replied(chat_id: int) -> None:
    await _set_field(chat_id, "last_owner_reply_at", time.time())


async def mark_bot_replied(chat_id: int) -> None:
    await _set_field(chat_id, "last_bot_reply_at", time.time())


def owner_active_in(memory: dict[str, Any], pause_minutes: int) -> bool:
    """Pure version of owner_recently_active() that works off an
    already-loaded memory dict, so a caller that already has `memory` in
    hand (e.g. from append_recent_message's return value) doesn't need a
    second DB read just to answer this question."""
    last = memory.get("last_owner_reply_at")
    if not last:
        return False
    return (time.time() - last) / 60 < pause_minutes


async def owner_recently_active(chat_id: int, pause_minutes: int) -> bool:
    return owner_active_in(await get_memory(chat_id), pause_minutes)


def drop_idle_locks(chat_ids: list[int]) -> None:
    """Periodic-cleanup hook: drops per-chat locks for chats that have gone
    quiet, so _chat_locks doesn't grow forever over a months-long process
    lifetime. Only drops a lock that isn't currently held — never removes
    one mid-use."""
    for chat_id in chat_ids:
        lock = _chat_locks.get(chat_id)
        if lock is not None and not lock.locked():
            _chat_locks.pop(chat_id, None)


async def delete_chat_memory(chat_id: int) -> None:
    """Wipe memory for a single chat — e.g. if the owner wants to 'forget' someone."""
    pool = _pool_or_raise()
    await pool.execute("DELETE FROM chats WHERE chat_id = $1", chat_id)


async def get_state(key: str) -> Optional[str]:
    pool = _pool_or_raise()
    row = await pool.fetchrow("SELECT value FROM bot_state WHERE key = $1", key)
    return row["value"] if row else None


async def set_state(key: str, value: str) -> None:
    pool = _pool_or_raise()
    await pool.execute(
        """
        INSERT INTO bot_state (key, value) VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        key,
        value,
    )


async def delete_state(key: str) -> None:
    pool = _pool_or_raise()
    await pool.execute("DELETE FROM bot_state WHERE key = $1", key)


# --- Inbox: a record of every incoming message the owner can review,
# mark read, or delete, independent of the per-chat memory blob above. ---


async def add_inbox_message(
    chat_id: int, user_name: str, message_text: str, is_important: bool, bot_reply: Optional[str]
) -> int:
    pool = _pool_or_raise()
    row = await pool.fetchrow(
        """
        INSERT INTO inbox_messages (chat_id, user_name, message_text, is_important, bot_reply)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        chat_id,
        user_name,
        message_text,
        is_important,
        bot_reply,
    )
    return row["id"]


async def list_unread_inbox(limit: int) -> list[asyncpg.Record]:
    pool = _pool_or_raise()
    return await pool.fetch(
        "SELECT * FROM inbox_messages WHERE is_read = FALSE ORDER BY created_at ASC LIMIT $1",
        limit,
    )


async def count_unread_inbox() -> int:
    pool = _pool_or_raise()
    row = await pool.fetchrow("SELECT COUNT(*) AS c FROM inbox_messages WHERE is_read = FALSE")
    return row["c"]


async def get_inbox_message(message_id: int) -> Optional[asyncpg.Record]:
    pool = _pool_or_raise()
    return await pool.fetchrow("SELECT * FROM inbox_messages WHERE id = $1", message_id)


async def mark_inbox_read(message_id: int) -> bool:
    pool = _pool_or_raise()
    result = await pool.execute(
        "UPDATE inbox_messages SET is_read = TRUE WHERE id = $1", message_id
    )
    return result.split()[-1] != "0"


async def mark_all_inbox_read() -> int:
    pool = _pool_or_raise()
    result = await pool.execute("UPDATE inbox_messages SET is_read = TRUE WHERE is_read = FALSE")
    return int(result.split()[-1])


async def delete_inbox_message(message_id: int) -> bool:
    pool = _pool_or_raise()
    result = await pool.execute("DELETE FROM inbox_messages WHERE id = $1", message_id)
    return result.split()[-1] != "0"