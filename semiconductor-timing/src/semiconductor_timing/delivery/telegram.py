from __future__ import annotations

import requests


def send_telegram(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id or token.endswith("replace_me"):
        raise RuntimeError("Telegram token/chat_id is missing")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    if response.status_code == 400:
        raise RuntimeError(
            "Telegram returned 400. Check TELEGRAM_CHAT_ID format and whether the chat/channel exists."
        )
    if response.status_code == 403:
        raise RuntimeError(
            "Telegram returned 403. The bot is not allowed to post there. "
            "Add the bot as a channel admin and enable post-message permission."
        )
    if response.status_code == 404:
        raise RuntimeError(
            "Telegram returned 404. Check TELEGRAM_BOT_TOKEN; do not include a 'bot' prefix."
        )
    if not response.ok:
        raise RuntimeError(f"Telegram send failed with HTTP {response.status_code}.")
