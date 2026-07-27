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

    Each platform handles its own message formatting (``build_payload``),
    HTTP headers (``build_headers``), and URL computation (``get_url``),
    including signing logic.
    """

    name: ClassVar[str]
    """Human-readable platform identifier (e.g. ``"dingtalk"``)."""

    def get_url(self) -> str:
        """Return the webhook URL to send the request to.

        The default implementation returns the URL passed at construction.
        Platforms that need per-request signing (e.g. DingTalk with HMAC)
        override this to append query parameters.
        """
        ...

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

    def get_url(self) -> str:
        """Return the webhook URL for the request.

        The default returns the URL passed at construction.
        Override in subclasses (e.g. DingTalk with signing) to append
        per-request query parameters.
        """
        return self._url

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

    # Status icons mapped to event types
    _ICONS: dict[str, str] = {
        "SyncStarted": "\U0001f504",         # 🔄
        "SyncCompleted": "✅",           # ✅
        "ResourceFailed": "❌",          # ❌
        "ResourceWritten": "\U0001f4dd",     # 📝
        "ResourceSkipped": "⏭️",    # ⏭️
        "ResourceFetchCompleted": "\U0001f4e5", # 📥
    }

    @staticmethod
    def _format_key_value(key: str, value: object, width: int = 10) -> str:
        """Format a key-value pair with aligned columns.

        ``width`` controls the key column width for alignment.
        """
        return f"  {key:<{width}} {value}"

    def _format_sync_started(self, event: SyncStarted) -> dict[str, Any]:
        icon = self._ICONS.get("SyncStarted", "")
        lines = [
            f"{icon} Sync Started",
            "",
            self._format_key_value("Resources", event.config_summary),
        ]
        return self._make_message("\n".join(lines), title=f"{icon} Sync Started")

    def _format_sync_completed(self, event: SyncCompleted) -> dict[str, Any]:
        icon = self._ICONS.get("SyncCompleted", "")
        # Try to parse the summary dict for detailed breakdown
        summary_text = event.summary
        lines = [f"{icon} Sync Completed", ""]
        if summary_text.startswith("{") and summary_text.endswith("}"):
            try:
                data = eval(summary_text)  # safe: dict literal from our own code
                if isinstance(data, dict):
                    for key in ("created", "updated", "skipped", "error"):
                        val = data.get(key, 0)
                        lines.append(self._format_key_value(key.capitalize(), val))
                    changed = data.get("created", 0) + data.get("updated", 0)
                    lines.append(self._format_key_value("Changed", changed))
                else:
                    lines.append(f"  {summary_text}")
            except Exception:
                lines.append(f"  {summary_text}")
        else:
            lines.append(f"  {summary_text}")
        return self._make_message("\n".join(lines), title=f"{icon} Sync Completed")

    def _format_resource_failed(self, event: ResourceFailed) -> dict[str, Any]:
        icon = self._ICONS.get("ResourceFailed", "")
        lines = [
            f"{icon} Resource Failed",
            "",
            self._format_key_value("Resource", event.resource_name),
            self._format_key_value("Stage", event.stage),
            self._format_key_value("Error", event.error),
        ]
        return self._make_message("\n".join(lines), title=f"{icon} Resource Failed")

    def _format_resource_written(self, event: ResourceWritten) -> dict[str, Any]:
        icon = self._ICONS.get("ResourceWritten", "")
        # Format bytes to human-readable
        bytes_val = event.bytes_written
        if bytes_val >= 1024 * 1024:
            size_str = f"{bytes_val / (1024 * 1024):.1f} MB"
        elif bytes_val >= 1024:
            size_str = f"{bytes_val / 1024:.1f} KB"
        else:
            size_str = f"{bytes_val} bytes"
        lines = [
            f"{icon} Resource Updated",
            "",
            self._format_key_value("Resource", event.resource_name),
            self._format_key_value("Path", event.path),
            self._format_key_value("Size", size_str),
        ]
        return self._make_message("\n".join(lines), title=f"{icon} Resource Updated")

    def _format_resource_skipped(self, event: ResourceSkipped) -> dict[str, Any]:
        icon = self._ICONS.get("ResourceSkipped", "")
        lines = [
            f"{icon} Resource Skipped",
            "",
            self._format_key_value("Resource", event.resource_name),
            self._format_key_value("Reason", "No changes detected"),
        ]
        return self._make_message("\n".join(lines), title=f"{icon} Resource Skipped")

    def _format_resource_fetch_completed(self, event: ResourceFetchCompleted) -> dict[str, Any]:
        icon = self._ICONS.get("ResourceFetchCompleted", "")
        bytes_val = event.bytes_downloaded
        if bytes_val >= 1024 * 1024:
            size_str = f"{bytes_val / (1024 * 1024):.1f} MB"
        elif bytes_val >= 1024:
            size_str = f"{bytes_val / 1024:.1f} KB"
        else:
            size_str = f"{bytes_val} bytes"
        lines = [
            f"{icon} Resource Fetched",
            "",
            self._format_key_value("Resource", event.resource_name),
            self._format_key_value("Size", size_str),
        ]
        return self._make_message("\n".join(lines), title=f"{icon} Resource Fetched")