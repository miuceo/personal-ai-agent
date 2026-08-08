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

import json
import time
from typing import Any, Optional

import asyncpg

from config import settings

_pool: Optional[asyncpg.Pool] = None

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


def _pool_or_raise() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized — call init_db() first.")
    return _pool


async def is_known_contact(chat_id: int) -> bool:
    """True if we've exchanged messages with this chat before."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("SELECT 1 FROM chats WHERE chat_id = $1", chat_id)
    return row is not None


async def get_memory(chat_id: int) -> dict[str, Any]:
    pool = _pool_or_raise()
    row = await pool.fetchrow("SELECT memory FROM chats WHERE chat_id = $1", chat_id)
    if row is None:
        return dict(EMPTY_MEMORY)
    return json.loads(row["memory"])


async def ensure_chat(chat_id: int, user_name: str) -> None:
    pool = _pool_or_raise()
    await pool.execute(
        """
        INSERT INTO chats (chat_id, user_name, memory, updated_at)
        VALUES ($1, $2, $3::jsonb, now())
        ON CONFLICT (chat_id) DO UPDATE SET user_name = EXCLUDED.user_name
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
    memory = await get_memory(chat_id)

    # 24-hour rule: if the gap since the last message is too long, this is
    # treated as a fresh short-term conversation — but the long-term summary
    # is intentionally NOT touched.
    last_at = memory.get("last_message_at")
    if last_at and (time.time() - last_at) > RECENT_CONTEXT_TTL_SECONDS:
        memory["recent_messages"] = []

    memory["recent_messages"].append({"role": role, "text": text, "ts": time.time()})
    memory["recent_messages"] = memory["recent_messages"][-limit:]
    memory["last_message_at"] = time.time()
    await save_memory(chat_id, memory)


async def update_summary(chat_id: int, new_summary: str) -> None:
    memory = await get_memory(chat_id)
    memory["summary"] = new_summary
    await save_memory(chat_id, memory)


async def mark_owner_replied(chat_id: int) -> None:
    memory = await get_memory(chat_id)
    memory["last_owner_reply_at"] = time.time()
    await save_memory(chat_id, memory)


async def mark_bot_replied(chat_id: int) -> None:
    memory = await get_memory(chat_id)
    memory["last_bot_reply_at"] = time.time()
    await save_memory(chat_id, memory)


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