"""WeChat Work (Enterprise WeChat) webhook platform."""

from __future__ import annotations

from typing import Any, ClassVar

from resource_sync.observer.webhook.base import WebhookPlatformBase
from resource_sync.plugin.registry import register_webhook_platform


@register_webhook_platform("wechat_work")
class WeChatWorkPlatform(WebhookPlatformBase):
    """WeChat Work robot webhook platform.

    Messages are formatted as WeChat Work markdown (``content`` field).
    """

    name: ClassVar[str] = "wechat_work"

    def _make_message(self, text: str, title: str) -> dict[str, Any]:
        return {
            "msgtype": "markdown",
            "markdown": {
                "content": f"# {title}\n{text}\n---\nResource Sync Engine",
            },
        }