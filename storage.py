"""
storage.py

SQLite persistence layer for the secretary bot.

We keep one row per chat (per person you talk to). Each row stores:
- a rolling memory summary (short paragraph, updated after every exchange)
- a short JSON list of the last few raw messages (for immediate context)
- the last time the owner personally replied in that chat (for the pause logic)
- the last time the bot itself replied (used in the /hisobot digest)

SQLite is used here because it needs zero setup for a 1-week prototype.
Later, this can be swapped for the Neon Postgres database used in the
n8n version, without changing the rest of the bot's logic — only the
functions in this file would need to change.
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "secretary.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                user_name TEXT,
                memory_summary TEXT DEFAULT '',
                recent_messages TEXT DEFAULT '[]',
                last_owner_reply_at REAL,
                last_bot_reply_at REAL,
                unread_since_owner_left INTEGER DEFAULT 0,
                updated_at REAL
            )
            """
        )


def get_chat(chat_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        return cur.fetchone()


def ensure_chat(chat_id: int, user_name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO chats (chat_id, user_name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET user_name = excluded.user_name
            """,
            (chat_id, user_name, time.time()),
        )


def append_recent_message(chat_id: int, role: str, text: str, limit: int) -> None:
    """Keep only the last `limit` raw messages for quick short-term context."""
    row = get_chat(chat_id)
    history = json.loads(row["recent_messages"]) if row else []
    history.append({"role": role, "text": text, "ts": time.time()})
    history = history[-limit:]
    with get_conn() as conn:
        conn.execute(
            "UPDATE chats SET recent_messages = ?, updated_at = ? WHERE chat_id = ?",
            (json.dumps(history, ensure_ascii=False), time.time(), chat_id),
        )


def get_recent_messages(chat_id: int) -> list[dict]:
    row = get_chat(chat_id)
    if not row or not row["recent_messages"]:
        return []
    return json.loads(row["recent_messages"])


def update_memory_summary(chat_id: int, new_summary: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE chats SET memory_summary = ?, updated_at = ? WHERE chat_id = ?",
            (new_summary, time.time(), chat_id),
        )


def mark_owner_replied(chat_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE chats SET last_owner_reply_at = ?, unread_since_owner_left = 0 WHERE chat_id = ?",
            (time.time(), chat_id),
        )


def mark_bot_replied(chat_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE chats SET last_bot_reply_at = ?, unread_since_owner_left = unread_since_owner_left + 1 WHERE chat_id = ?",
            (time.time(), chat_id),
        )


def owner_recently_active(chat_id: int, pause_minutes: int) -> bool:
    """True if the owner personally replied in this chat within the pause window."""
    row = get_chat(chat_id)
    if not row or not row["last_owner_reply_at"]:
        return False
    elapsed_minutes = (time.time() - row["last_owner_reply_at"]) / 60
    return elapsed_minutes < pause_minutes


def get_all_chats_with_bot_activity() -> list[sqlite3.Row]:
    """Used by the /hisobot digest — chats where the bot replied on the owner's behalf."""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM chats WHERE unread_since_owner_left > 0 ORDER BY updated_at DESC"
        )
        return cur.fetchall()
