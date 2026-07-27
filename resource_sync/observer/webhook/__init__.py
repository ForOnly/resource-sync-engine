"""Webhook observer — sends event notifications to external platforms.

Supports pluggable platform strategies. Each platform (DingTalk, WeChat
Work, Slack, Generic) is a separate plugin registered via
``@register_webhook_platform`` and can be extended with custom
implementations.

Configured via ``engine.observers`` in ``config.yaml``:

.. code-block:: yaml

   engine:
     observers:
       - type: webhook
         platform: dingtalk
         url: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
         secret: "your-secret"          # optional, for HMAC-SHA256 signing
         events:                         # optional event filter (default: all)
           - SyncCompleted
           - ResourceFailed

The ``url`` and ``secret`` fields support ``${ENV_VAR}`` substitution
for environment variables, making them compatible with GitHub Actions
secrets and other CI/CD systems.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import httpx

from resource_sync.domain.events import Event
from resource_sync.observer.webhook import base  # noqa: F401 — ensure base module is importable
from resource_sync.observer.webhook import dingtalk  # noqa: F401
from resource_sync.observer.webhook import generic  # noqa: F401
from resource_sync.observer.webhook import slack  # noqa: F401
from resource_sync.observer.webhook import wechat_work  # noqa: F401
from resource_sync.plugin.registry import register_observer, register_webhook_platform

_LOGGER = logging.getLogger(__name__)

# Default timeout for webhook HTTP requests
_WEBHOOK_TIMEOUT = 10.0


@register_observer
class WebhookObserver:
    """Observer that sends event notifications via webhook.

    Each instance represents a single webhook target. Multiple instances
    can be created from the config to target different platforms.

    Delegates message formatting and header signing to the configured
    platform plugin.
    """

    name: ClassVar[str] = "webhook"

    def __init__(
        self,
        platform: str,
        url: str,
        secret: str = "",
        event_filter: list[str] | None = None,
    ) -> None:
        from resource_sync.plugin.registry import get_registry

        self._platform = platform
        self._url = url
        self._secret = secret
        self._event_filter = event_filter

        # Look up the platform plugin from the registry
        registry = get_registry()
        platform_cls = registry.get_webhook_platform(platform)
        self._platform_impl = platform_cls(url=url, secret=secret)

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(_WEBHOOK_TIMEOUT),
        )

    @classmethod
    def configure(cls, config: dict[str, Any]) -> WebhookObserver:
        """Create a WebhookObserver from a config dict.

        Expected keys:
            - ``platform`` (str): dingtalk, wechat_work, slack, or generic
            - ``url`` (str): webhook URL (supports ``${ENV_VAR}`` substitution)
            - ``secret`` (str, optional): secret for platform signing
            - ``events`` (list[str], optional): event type names to filter on
        """
        platform = str(config.get("platform", "generic"))
        url = str(config.get("url", ""))
        secret = str(config.get("secret", ""))
        raw_events = config.get("events")
        event_filter: list[str] | None = None
        if raw_events is not None and isinstance(raw_events, list):
            event_filter = [str(e) for e in raw_events]
        return cls(platform=platform, url=url, secret=secret, event_filter=event_filter)

    async def on_event(self, event: Event) -> None:
        """Handle a domain event by sending a webhook notification.

        If the event type is filtered out, this is a no-op.
        HTTP errors are logged but not propagated.
        """
        # Apply event filter
        if self._event_filter is not None:
            if type(event).__name__ not in self._event_filter:
                return

        # Delegate payload building to the platform plugin
        payload = self._platform_impl.build_payload(event)
        if payload is None:
            return  # Skip unhandled event types

        # Delegate header building to the platform plugin
        headers = self._platform_impl.build_headers(payload)

        # Get the request URL (platform may add signing query params)
        request_url = self._platform_impl.get_url()

        # Send the webhook request
        try:
            response = await self._client.post(request_url, json=payload, headers=headers)
            response.raise_for_status()
            _LOGGER.debug(
                "Webhook sent (%s/%s) — %s",
                self._platform, type(event).__name__, response.status_code,
            )
        except httpx.HTTPError as e:
            _LOGGER.error(
                "Webhook notification failed (%s/%s): %s",
                self._platform, type(event).__name__, e,
            )