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
        return {
            "event": title.lower().replace(" ", "_"),
            "title": title,
            "message": text,
            "timestamp": time.time(),
        }