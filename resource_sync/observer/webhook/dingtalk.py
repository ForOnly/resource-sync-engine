"""DingTalk webhook platform — robot with optional HMAC-SHA256 signing."""

from __future__ import annotations

import hashlib
import hmac
import time
from base64 import b64encode
from typing import Any, ClassVar

from resource_sync.observer.webhook.base import WebhookPlatformBase
from resource_sync.plugin.registry import register_webhook_platform


@register_webhook_platform("dingtalk")
class DingTalkPlatform(WebhookPlatformBase):
    """DingTalk robot webhook platform.

    Supports optional HMAC-SHA256 signing via the ``secret`` parameter.
    Messages are formatted as DingTalk markdown.
    """

    name: ClassVar[str] = "dingtalk"

    def _make_message(self, text: str, title: str) -> dict[str, Any]:
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### {title}\n\n{text}",
            },
        }

    def build_headers(self, payload: dict[str, Any]) -> dict[str, str]:
        """Add DingTalk HMAC-SHA256 signature headers if a secret is set."""
        headers = super().build_headers(payload)

        if self._secret:
            timestamp = str(int(time.time() * 1000))
            sign_string = f"{timestamp}\n{self._secret}"
            signature = b64encode(
                hmac.new(
                    self._secret.encode("utf-8"),
                    sign_string.encode("utf-8"),
                    hashlib.sha256,
                ).digest()
            ).decode("utf-8")
            headers["timestamp"] = timestamp
            headers["sign"] = signature

        return headers