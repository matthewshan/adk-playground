"""Discord tool — incoming webhook delivery."""

from __future__ import annotations

import os

import requests


def send_discord(message: str) -> str:
    """Post a message to a Discord channel via incoming webhook.

    Requires the DISCORD_WEBHOOK_URL environment variable.

    Args:
        message: The formatted briefing text to post.

    Returns:
        "Sent" on success. Raises requests.HTTPError on failure.
    """
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    # Discord's per-message limit is 2000 characters.
    payload = {"content": message[:2000]}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
    return "Sent"
