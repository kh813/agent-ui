#!/usr/bin/env python3
"""
Send a plain-text message to a Google Chat space via an Incoming Webhook.

Usage:
  python3 notify_chat.py "<message>"

Configured via config.toml's [notifications] chat_webhook_url. Set up with
the `notify-chat` skill, which guides you through creating a Chat space and
issuing the webhook URL.
"""
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parents[2] / "python"))

import requests
from config import CHAT_WEBHOOK_URL  # noqa: E402


def send(message: str) -> bool:
    if not CHAT_WEBHOOK_URL:
        print(
            "[notify_chat] chat_webhook_url is not set in config.toml. "
            "Run the notify-chat skill to set it up. Skipping send."
        )
        return False

    resp = requests.post(CHAT_WEBHOOK_URL, json={"text": message}, timeout=15)
    if resp.status_code >= 300:
        print(f"[notify_chat] Failed to send ({resp.status_code}): {resp.text[:300]}")
        return False

    print("[notify_chat] Sent.")
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python3 notify_chat.py "<message>"')
        sys.exit(1)

    ok = send(sys.argv[1])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
