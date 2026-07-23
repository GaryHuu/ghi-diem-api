"""Best-effort Telegram notification when a match is created.

Disabled unless TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set. Sends in a
daemon thread with a short timeout and swallows every error: a notification
must never slow down or break match creation.
"""
import json
import logging
import os
import threading
import urllib.request

logger = logging.getLogger(__name__)


def notify_match_created(match) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    dashboard_url = os.environ.get(
        "DASHBOARD_URL", "https://www.ghidiem.online/dashboard"
    )
    text = (
        f"🎴 Trận mới: {match.name}\n"
        f"Device: {match.device_id}\n"
        f"{dashboard_url}"
    )
    threading.Thread(target=_send, args=(token, chat_id, text), daemon=True).start()


def _send(token: str, chat_id: str, text: str) -> None:
    try:
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=5)
    except Exception:
        logger.warning("Telegram notification failed", exc_info=True)
