"""Generic webhook platform — simple JSON format."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from resource_sync.observer.webhook.base import WebhookPlatformBase
from resource_sync.plugin.registry import register_webhook_platform


@register_webhook_platform("generic")
class GenericPlatform(WebhookPlatformBase):
    """Generic JSON webhook platform.

    Sends a flat JSON object with ``event``, ``title``, ``message``,
    and ``timestamp`` fields. Compatible with any receiver that accepts
    a JSON POST body.
    """

    name: ClassVar[str] = "generic"

    def _make_message(self, text: str, title: str) -> dict[str, Any]:
        # Strip the first line (title + emoji) from text for the message
        # The first line is the header, remaining lines are the body
        lines = text.split("\n")
        # Filter out empty lines for the body
        body_lines = [line for line in lines[1:] if line.strip()]
        return {
            "event": title.split()[-1].lower().replace(" ", "_")
            if " " in title
            else title.lower().replace(" ", "_"),
            "title": title,
            "message": "\n".join(body_lines) if body_lines else "",
            "timestamp": time.time(),
        }