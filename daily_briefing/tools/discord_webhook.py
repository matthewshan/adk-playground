"""Discord tool — delivers the briefing via incoming webhook."""

from __future__ import annotations

import os

from daily_briefing.apis.discord import post_message


def send_discord(message: str) -> str:
    """Post a message to a Discord channel via incoming webhook.

    Requires the DISCORD_WEBHOOK_URL environment variable.

    Args:
        message: The formatted briefing text to post.

    Returns:
        "Sent" on success. Raises requests.HTTPError on failure.
    """
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    post_message(webhook_url, message[:2000])  # Discord limit: 2000 chars
    return "Sent"
