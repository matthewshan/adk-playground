"""Discord incoming webhook API client."""

from __future__ import annotations

import requests


def post_message(webhook_url: str, content: str) -> None:
    """POST a message to a Discord channel via incoming webhook.

    Args:
        webhook_url: Full Discord webhook URL.
        content: Message text. Caller is responsible for respecting the
                 2000-character Discord limit before calling this function.

    Raises:
        requests.HTTPError: On non-2xx responses.
    """
    resp = requests.post(webhook_url, json={"content": content}, timeout=10)
    resp.raise_for_status()
