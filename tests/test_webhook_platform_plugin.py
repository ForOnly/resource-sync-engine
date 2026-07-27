"""Tests for the webhook platform plugin architecture.

Verifies that:
- Platforms can be registered and looked up via the plugin registry.
- Unknown platform names raise ``PluginNotFoundError``.
- Custom platforms can be registered and used as WebhookObserver strategies.
- Duplicate platform names raise ``PluginConflictError``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from resource_sync.domain.events import SyncCompleted
from resource_sync.observer.webhook import WebhookObserver
from resource_sync.observer.webhook.base import WebhookPlatformBase
from resource_sync.plugin.registry import (
    PluginConflictError,
    PluginNotFoundError,
    get_registry,
    register_webhook_platform,
)


class TestPlatformRegistration:
    """Webhook platform registration in the plugin registry."""

    def test_builtin_platforms_registered(self) -> None:
        """All built-in platforms should be registered."""
        registry = get_registry()
        for name in ("dingtalk", "wechat_work", "slack", "generic"):
            cls = registry.get_webhook_platform(name)
            assert cls is not None
            assert cls.name == name

    def test_get_unknown_platform_raises(self) -> None:
        """Looking up an unknown platform should raise ``PluginNotFoundError``."""
        registry = get_registry()
        with pytest.raises(PluginNotFoundError, match="No webhook platform: 'nonexistent'"):
            registry.get_webhook_platform("nonexistent")

    def test_duplicate_registration_raises(self) -> None:
        """Registering a duplicate platform name should raise ``PluginConflictError``."""
        registry = get_registry()

        class DuplicatePlatform(WebhookPlatformBase):
            name = "generic"

        with pytest.raises(PluginConflictError, match="already registered"):
            registry.register_webhook_platform("generic", DuplicatePlatform)


class TestCustomPlatform:
    """Custom (user-defined) webhook platforms."""

    def test_register_and_use_custom_platform(self) -> None:
        """A custom platform can be registered and used as a WebhookObserver strategy."""

        @register_webhook_platform("custom_test")
        class CustomPlatform(WebhookPlatformBase):
            name = "custom_test"

            def _make_message(self, text: str, title: str) -> dict:
                return {
                    "custom": True,
                    "title": title,
                    "text": text,
                }

        # Verify it's in the registry
        registry = get_registry()
        cls = registry.get_webhook_platform("custom_test")
        assert cls is CustomPlatform

        # Create a WebhookObserver using the custom platform
        observer = WebhookObserver(
            platform="custom_test",
            url="https://custom.example.com/hook",
        )
        assert observer._platform == "custom_test"
        assert observer._url == "https://custom.example.com/hook"

        # Verify it formats messages correctly
        event = SyncCompleted(summary="custom sync done")
        payload = observer._platform_impl.build_payload(event)
        assert payload is not None
        assert payload["custom"] is True
        assert "custom sync done" in payload["text"]

        # Verify it sends webhooks correctly
        with patch.object(observer, "_client") as mock_client:
            mock_client.post = AsyncMock()
            mock_client.post.return_value.raise_for_status = lambda: None
            import asyncio
            asyncio.run(observer.on_event(event))
            mock_client.post.assert_called_once()

    def test_configure_with_custom_platform(self) -> None:
        """``configure()`` should work with a custom platform."""

        @register_webhook_platform("custom_configure")
        class CustomConfigurePlatform(WebhookPlatformBase):
            name = "custom_configure"

            def _make_message(self, text: str, title: str) -> dict:
                return {"custom": True, "msg": text}

        observer = WebhookObserver.configure({
            "platform": "custom_configure",
            "url": "https://example.com/hook",
            "secret": "my-secret",
            "events": ["SyncCompleted"],
        })
        assert observer._platform == "custom_configure"
        assert observer._url == "https://example.com/hook"
        assert observer._secret == "my-secret"
        assert observer._event_filter == ["SyncCompleted"]


class TestPlatformProtocol:
    """Verifies that platforms satisfy the WebhookPlatform protocol."""

    def test_platforms_are_runtime_checkable(self) -> None:
        """Platform instances should pass ``isinstance`` checks against the protocol."""
        from resource_sync.observer.webhook.base import WebhookPlatform

        registry = get_registry()
        for name in ("dingtalk", "wechat_work", "slack", "generic"):
            cls = registry.get_webhook_platform(name)
            instance = cls(url="https://example.com/hook")
            assert isinstance(instance, WebhookPlatform), f"{name} does not satisfy WebhookPlatform"