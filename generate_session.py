"""
generate_session.py

Run this ONCE, locally, on your own computer:

    python generate_session.py

It logs into your Telegram account interactively (asks for the code sent
to your app, and your 2FA password if you have one), then prints a long
text string — your session, encoded as text instead of a file.

Copy that string and set it as the TELEGRAM_SESSION environment variable
in Kuberns (and in your local .env, if you want). This lets main.py log
in on the server WITHOUT needing an interactive prompt there.

Treat this string exactly like a password — anyone who has it can access
your Telegram account. Never commit it to GitHub or share it.
"""

from telethon import TelegramClient
from telethon.sessions import StringSession

from config import settings


def main() -> None:
    with TelegramClient(StringSession(), settings.api_id, settings.api_hash) as client:
        client.start(phone=settings.phone_number)
        session_string = client.session.save()
        print("\n" + "=" * 60)
        print("SESSIYANGIZ TAYYOR — quyidagi qatorni TELEGRAM_SESSION")
        print("nomli muhit o'zgaruvchisiga (Kuberns va .env) joylashtiring:")
        print("=" * 60 + "\n")
        print(session_string)
        print("\n" + "=" * 60)


if __name__ == "__main__":
    main()