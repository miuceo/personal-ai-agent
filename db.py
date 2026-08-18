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
# One lock per chat serializes them.
_chat_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

RECENT_CONTEXT_TTL_SECONDS = 24 * 60 * 60

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
            CREATE TABLE IF NOT EXISTS unread_entries (
                id SERIAL PRIMARY KEY,
                user_name TEXT,
                their_message TEXT,
                bot_reply TEXT,
                is_important BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
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


async def append_recent_message(chat_id: int, role: str, text: str, limit: int) -> None:
    async with _chat_locks[chat_id]:
        memory = await get_memory(chat_id)

        # 24-hour rule: if the gap since the last message is too long, this is
        # treated as a fresh short-term conversation — but the long-term summary
        # is intentionally NOT touched.
        last_at = memory.get("last_message_at")
        if last_at and (time.time() - last_at) > RECENT_CONTEXT_TTL_SECONDS:
            memory["recent_messages"] = []

        memory["recent_messages"].append({"role": role, "text": text, "ts": time.time()})
        memory["recent_messages"] = memory["recent_messages"][-max(limit, 1) :]
        memory["last_message_at"] = time.time()
        await save_memory(chat_id, memory)


async def _set_field(chat_id: int, key: str, value: Any) -> None:
    async with _chat_locks[chat_id]:
        memory = await get_memory(chat_id)
        memory[key] = value
        await save_memory(chat_id, memory)


async def update_summary(chat_id: int, new_summary: str) -> None:
    await _set_field(chat_id, "summary", new_summary)


async def mark_owner_replied(chat_id: int) -> None:
    await _set_field(chat_id, "last_owner_reply_at", time.time())


async def mark_bot_replied(chat_id: int) -> None:
    await _set_field(chat_id, "last_bot_reply_at", time.time())


async def owner_recently_active(chat_id: int, pause_minutes: int) -> bool:
    memory = await get_memory(chat_id)
    last = memory.get("last_owner_reply_at")
    if not last:
        return False
    return (time.time() - last) / 60 < pause_minutes


async def delete_chat_memory(chat_id: int) -> None:
    """Wipe memory for a single chat — e.g. if the owner wants to 'forget' someone."""
    pool = _pool_or_raise()
    await pool.execute("DELETE FROM chats WHERE chat_id = $1", chat_id)


async def add_unread_entry(
    user_name: str, their_message: str, bot_reply: str, is_important: bool
) -> None:
    """Records a reply the bot sent on the owner's behalf, for the /messages digest."""
    pool = _pool_or_raise()
    await pool.execute(
        """
        INSERT INTO unread_entries (user_name, their_message, bot_reply, is_important)
        VALUES ($1, $2, $3, $4)
        """,
        user_name,
        their_message,
        bot_reply,
        is_important,
    )


async def get_unread_entries() -> list[dict[str, Any]]:
    pool = _pool_or_raise()
    rows = await pool.fetch(
        "SELECT user_name, their_message, bot_reply, is_important FROM unread_entries ORDER BY created_at"
    )
    return [dict(row) for row in rows]


async def clear_unread_entries() -> int:
    """Deletes all unread entries, returns how many were removed."""
    pool = _pool_or_raise()
    result = await pool.execute("DELETE FROM unread_entries")
    # asyncpg returns e.g. "DELETE 3"
    return int(result.split()[-1])