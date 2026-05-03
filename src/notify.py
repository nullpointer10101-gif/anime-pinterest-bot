import os
import requests


def send_telegram(message: str):
    """Send a message to your Telegram chat. Fails silently if not configured."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[notify] Telegram not configured, skipping notification")
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        print("[notify] Telegram message sent")
    except Exception as e:
        print(f"[notify] Telegram send failed: {e}")
