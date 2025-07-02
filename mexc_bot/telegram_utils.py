import os
import time
import requests

TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT = os.getenv("TG_CHAT_ID")


def tg_send(
    text: str, parse_mode: str = "Markdown", silent: bool = False
) -> None:
    """Send a simple Telegram message if credentials are set."""
    if not (TG_TOKEN and TG_CHAT):
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT,
        "text": text,
        "parse_mode": parse_mode,
        "disable_notification": silent,
    }
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=3)
            if r.status_code == 200:
                return
        except requests.RequestException:
            time.sleep(1)
