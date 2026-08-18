"""
unread_store.py

A simple JSON file acting as an "unread inbox digest" — every time the bot
replies on the owner's behalf, an entry is appended here. The owner can
later fetch the list with /messages and clear it with /read-all.

This lives on local disk. That's safe on a persistent VM (e.g. the Google
Cloud e2-micro instance this project is deployed to) but would NOT be safe
on platforms that wipe local disk between deploys/restarts.
"""

import json
import time
from pathlib import Path

STORE_PATH = Path(__file__).parent / "unread.json"


def _load() -> list[dict]:
    if not STORE_PATH.exists():
        return []
    try:
        with STORE_PATH.open("r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        # A truncated file (e.g. killed mid-write) must not take the bot down.
        return []
    return entries if isinstance(entries, list) else []


def _save(entries: list[dict]) -> None:
    # Write-then-rename so a crash can never leave a half-written digest.
    tmp_path = STORE_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    tmp_path.replace(STORE_PATH)


def append(user_name: str, their_message: str, bot_reply: str, is_important: bool) -> None:
    entries = _load()
    entries.append(
        {
            "user_name": user_name,
            "their_message": their_message,
            "bot_reply": bot_reply,
            "is_important": is_important,
            "ts": time.time(),
        }
    )
    _save(entries)


def get_all() -> list[dict]:
    return _load()


def clear() -> int:
    """Wipes the file, returns how many entries were removed."""
    entries = _load()
    _save([])
    return len(entries)


def format_digest(entries: list[dict]) -> str:
    if not entries:
        return "O'qilmagan xabarlar yo'q."

    lines = ["📋 O'qilmagan xabarlar:\n"]
    for e in entries:
        flag = "🔴" if e.get("is_important") else "🟢"
        lines.append(
            f"{flag} {e.get('user_name', 'Noma‘lum')}\n"
            f"Ular: {e.get('their_message', '')}\n"
            f"Men javob berdim: {e.get('bot_reply', '')}"
        )
    return "\n\n".join(lines)