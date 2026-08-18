"""
unread_store.py

Formats the "unread inbox digest" the owner sees via /messages. The
entries themselves are persisted in Postgres (see db.add_unread_entry /
db.get_unread_entries / db.clear_unread_entries) so they survive
redeploys and restarts, instead of living on local disk.
"""


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
