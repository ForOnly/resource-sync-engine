"""DingTalk webhook platform — robot with optional HMAC-SHA256 signing.

DingTalk requires the HMAC-SHA256 signature to be passed as URL query
parameters (``timestamp`` and ``sign``), NOT as HTTP headers. The
signature is computed per-request in ``get_url()``.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from base64 import b64encode
from typing import Any, ClassVar
from urllib.parse import urlencode, urlparse, urlunparse

from resource_sync.observer.webhook.base import WebhookPlatformBase
from resource_sync.plugin.registry import register_webhook_platform


@register_webhook_platform("dingtalk")
class DingTalkPlatform(WebhookPlatformBase):
    """DingTalk robot webhook platform.

    Supports optional HMAC-SHA256 signing via the ``secret`` parameter.
    When a secret is set, ``get_url()`` appends ``timestamp`` and ``sign``
    query parameters to the webhook URL as required by the DingTalk API.

    Messages are formatted as DingTalk markdown.
    """

    name: ClassVar[str] = "dingtalk"

    def _make_message(self, text: str, title: str) -> dict[str, Any]:
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"# {title}\n\n{text}\n\n---\n*Resource Sync Engine*",
            },
        }

    def get_url(self) -> str:
        """Append DingTalk HMAC-SHA256 signature query parameters.

        If a secret is configured, computes the signature and returns
        the webhook URL with ``timestamp`` and ``sign`` query parameters
        appended. Otherwise returns the URL unchanged.
        """
        if not self._secret:
            return self._url

        timestamp = str(int(time.time() * 1000))
        sign_string = f"{timestamp}\n{self._secret}"
        signature = b64encode(
            hmac.new(
                self._secret.encode("utf-8"),
                sign_string.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        # Append timestamp and sign as query parameters
        parsed = urlparse(self._url)
        query = parsed.query
        extra_params = urlencode({"timestamp": timestamp, "sign": signature})
        new_query = f"{query}&{extra_params}" if query else extra_params
        return urlunparse(parsed._replace(query=new_query))