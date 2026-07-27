"""Slack webhook platform — Incoming Webhook format."""

from __future__ import annotations

from typing import Any, ClassVar

from resource_sync.observer.webhook.base import WebhookPlatformBase
from resource_sync.plugin.registry import register_webhook_platform


@register_webhook_platform("slack")
class SlackPlatform(WebhookPlatformBase):
    """Slack Incoming Webhook platform.

    Messages use Slack's ``text`` field with mrkdwn-style formatting.
    """

    name: ClassVar[str] = "slack"

    def _make_message(self, text: str, title: str) -> dict[str, Any]:
        return {
            "text": f"*{title}*\n{text}",
            "mrkdwn": True,
        }