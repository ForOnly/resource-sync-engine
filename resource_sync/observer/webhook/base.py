"""Webhook platform protocol and base class.

Webhook platforms are strategy plugins that implement platform-specific
message formatting and HTTP header signing. Each platform is registered
via ``@register_webhook_platform`` and looked up by name at runtime.

To add a custom platform:

1. Create a class implementing ``WebhookPlatform`` (or subclassing
   ``WebhookPlatformBase``).
2. Decorate it with ``@register_webhook_platform("my_platform")``.
3. Ensure the module is imported (add it to the webhook package's
   ``__init__.py`` or a plugin discovery path).
"""

from __future__ import annotations

from typing import Any, ClassVar, Protocol, runtime_checkable

from resource_sync.domain.events import Event


@runtime_checkable
class WebhookPlatform(Protocol):
    """Protocol for a webhook platform strategy.

    Each platform handles its own message formatting (``build_payload``)
    and HTTP headers (``build_headers``), including signing logic.
    """

    name: ClassVar[str]
    """Human-readable platform identifier (e.g. ``"dingtalk"``)."""

    def build_payload(self, event: Event) -> dict[str, Any] | None:
        """Build the JSON payload for the webhook request.

        Returns ``None`` for event types this platform does not handle.
        """
        ...

    def build_headers(self, payload: dict[str, Any]) -> dict[str, str]:
        """Build HTTP headers for the webhook request.

        Includes at minimum ``Content-Type: application/json``.
        May add platform-specific signing headers.
        """
        ...


class WebhookPlatformBase:
    """Base class for webhook platform implementations.

    Provides common ``_make_message`` helper and event routing.
    Subclasses override ``_make_message`` to return platform-specific
    payload shapes.
    """

    name: ClassVar[str] = ""

    def __init__(self, url: str, secret: str = "") -> None:
        self._url = url
        self._secret = secret

    # ─── To be overridden ───

    def _make_message(self, text: str, title: str) -> dict[str, Any]:
        """Build the platform-specific message payload from text and title.

        Must be overridden by subclasses to return the correct shape
        for the target platform (e.g. DingTalk markdown, Slack text).
        """
        raise NotImplementedError  # pragma: no cover

    # ─── Protocol implementation ───

    def build_payload(self, event: Event) -> dict[str, Any] | None:
        """Build the platform-specific message payload.

        Routes events to format methods by type.
        Returns ``None`` for unhandled event types.
        """
        from resource_sync.domain.events import (
            ResourceFailed,
            ResourceFetchCompleted,
            ResourceSkipped,
            ResourceWritten,
            SyncCompleted,
            SyncStarted,
        )

        t = type(event)
        formatter = {
            SyncStarted: self._format_sync_started,
            SyncCompleted: self._format_sync_completed,
            ResourceFailed: self._format_resource_failed,
            ResourceWritten: self._format_resource_written,
            ResourceSkipped: self._format_resource_skipped,
            ResourceFetchCompleted: self._format_resource_fetch_completed,
        }
        fmt = formatter.get(t)
        if fmt is None:
            return None
        return fmt(event)

    def build_headers(self, payload: dict[str, Any]) -> dict[str, str]:
        """Build HTTP headers for the webhook request.

        Returns a basic ``Content-Type: application/json`` header.
        Override in subclasses for platform-specific signing (e.g. DingTalk).
        """
        return {
            "Content-Type": "application/json",
        }

    # ─── Format helpers ───

    def _format_sync_started(self, event: SyncStarted) -> dict[str, Any]:
        text = f"Sync Started: {event.config_summary}"
        return self._make_message(text, title="Sync Started")

    def _format_sync_completed(self, event: SyncCompleted) -> dict[str, Any]:
        text = f"Sync Completed: {event.summary}"
        return self._make_message(text, title="Sync Completed")

    def _format_resource_failed(self, event: ResourceFailed) -> dict[str, Any]:
        text = f"Resource Failed: {event.resource_name}\nError: {event.error}\nStage: {event.stage}"
        return self._make_message(text, title="Resource Failed")

    def _format_resource_written(self, event: ResourceWritten) -> dict[str, Any]:
        text = (
            f"Resource Written: {event.resource_name}\n"
            f"Path: {event.path}\n"
            f"Bytes: {event.bytes_written}"
        )
        return self._make_message(text, title="Resource Updated")

    def _format_resource_skipped(self, event: ResourceSkipped) -> dict[str, Any]:
        text = f"Resource Skipped: {event.resource_name} (unchanged)"
        return self._make_message(text, title="Resource Skipped")

    def _format_resource_fetch_completed(self, event: ResourceFetchCompleted) -> dict[str, Any]:
        text = f"Fetched: {event.resource_name} ({event.bytes_downloaded} bytes)"
        return self._make_message(text, title="Resource Fetched")