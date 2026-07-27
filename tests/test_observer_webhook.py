"""Tests for WebhookObserver and webhook platform plugins.

Platform plugins (DingTalk, WeChat Work, Slack, Generic) are tested
individually for their message format and signing logic. The
WebhookObserver is tested for event filtering, error handling, and
the configure() factory method.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from resource_sync.domain.events import (
    ResourceFailed,
    ResourceFetchCompleted,
    ResourceSkipped,
    ResourceWritten,
    SyncCompleted,
    SyncStarted,
)
from resource_sync.observer.webhook import WebhookObserver
from resource_sync.observer.webhook.dingtalk import DingTalkPlatform
from resource_sync.observer.webhook.generic import GenericPlatform
from resource_sync.observer.webhook.slack import SlackPlatform
from resource_sync.observer.webhook.wechat_work import WeChatWorkPlatform


# ─── Fixtures ───


@pytest.fixture
def generic_observer() -> WebhookObserver:
    return WebhookObserver(
        platform="generic",
        url="https://hooks.example.com/webhook",
        secret="",
    )


@pytest.fixture
def dingtalk_observer() -> WebhookObserver:
    return WebhookObserver(
        platform="dingtalk",
        url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
        secret="my-secret",
    )


@pytest.fixture
def wechat_observer() -> WebhookObserver:
    return WebhookObserver(
        platform="wechat_work",
        url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
    )


@pytest.fixture
def slack_observer() -> WebhookObserver:
    return WebhookObserver(
        platform="slack",
        url="https://hooks.slack.com/services/T00/B00/xxx",
    )


@pytest.fixture
def filtered_observer() -> WebhookObserver:
    return WebhookObserver(
        platform="generic",
        url="https://hooks.example.com/webhook",
        event_filter=["SyncCompleted", "ResourceFailed"],
    )


# ─── Platform-specific message format tests ───


class TestPlatformFormats:
    """Platform-specific message formatting, tested via platform plugins."""

    def test_slack_format(self) -> None:
        """Slack messages should use ``text`` field."""
        platform = SlackPlatform(url="https://hooks.slack.com/xxx")
        event = SyncCompleted(summary="5 resources synced")
        payload = platform.build_payload(event)
        assert payload is not None
        assert "text" in payload
        assert "Sync Completed" in payload["text"]

    def test_slack_resource_failed(self) -> None:
        """Slack failure messages should include error details."""
        platform = SlackPlatform(url="https://hooks.slack.com/xxx")
        event = ResourceFailed(resource_name="r1", error="Timeout", stage="fetch")
        payload = platform.build_payload(event)
        assert payload is not None
        assert "Resource Failed" in payload["text"]
        assert "Timeout" in payload["text"]

    def test_dingtalk_format(self) -> None:
        """DingTalk messages should use markdown format."""
        platform = DingTalkPlatform(url="https://oapi.dingtalk.com/robot/send?token=xxx")
        event = SyncCompleted(summary="3 created, 2 updated")
        payload = platform.build_payload(event)
        assert payload is not None
        assert payload["msgtype"] == "markdown"
        assert "markdown" in payload
        assert "title" in payload["markdown"]
        assert "text" in payload["markdown"]

    def test_dingtalk_resource_written(self) -> None:
        """DingTalk written messages should include file details."""
        platform = DingTalkPlatform(url="https://oapi.dingtalk.com/robot/send?token=xxx")
        event = ResourceWritten(resource_name="r1", path="/tmp/f", bytes_written=100)
        payload = platform.build_payload(event)
        assert payload is not None
        assert payload["msgtype"] == "markdown"
        assert "r1" in payload["markdown"]["text"]
        assert "/tmp/f" in payload["markdown"]["text"]

    def test_wechat_work_format(self) -> None:
        """WeChat Work messages should use markdown format."""
        platform = WeChatWorkPlatform(url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx")
        event = SyncStarted(config_summary="10 resources")
        payload = platform.build_payload(event)
        assert payload is not None
        assert payload["msgtype"] == "markdown"
        assert "content" in payload["markdown"]

    def test_generic_format(self) -> None:
        """Generic messages should include event, title, message, timestamp."""
        platform = GenericPlatform(url="https://hooks.example.com/webhook")
        event = SyncCompleted(summary="all done")
        payload = platform.build_payload(event)
        assert payload is not None
        assert "event" in payload
        assert "title" in payload
        assert "message" in payload
        assert "timestamp" in payload


class TestDingTalkSigning:
    """DingTalk HMAC-SHA256 signing, tested via the platform plugin."""

    def test_signing_headers_present(self) -> None:
        """DingTalk with secret should include timestamp and sign headers."""
        platform = DingTalkPlatform(
            url="https://oapi.dingtalk.com/robot/send?token=xxx",
            secret="my-secret",
        )
        headers = platform.build_headers({})
        assert "timestamp" in headers
        assert "sign" in headers
        assert headers["Content-Type"] == "application/json"

    def test_no_secret_no_signing(self) -> None:
        """Without a secret, no signing headers should be added."""
        platform = GenericPlatform(url="https://hooks.example.com/webhook")
        headers = platform.build_headers({})
        assert "timestamp" not in headers
        assert "sign" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_signing_format(self) -> None:
        """The sign header should be a valid base64 string."""
        import base64

        platform = DingTalkPlatform(
            url="https://oapi.dingtalk.com/robot/send?token=xxx",
            secret="my-secret",
        )
        headers = platform.build_headers({})
        try:
            decoded = base64.b64decode(headers["sign"])
            assert len(decoded) == 32  # SHA-256 is 32 bytes
        except Exception:
            pytest.fail("Sign header is not valid base64")


class TestEventFilter:
    """Event filtering on WebhookObserver."""

    async def test_filter_blocks_unwanted(self, filtered_observer: WebhookObserver) -> None:
        """Events not in the filter should be skipped."""
        event = ResourceWritten(resource_name="r1", path="/tmp/f", bytes_written=100)
        with patch.object(filtered_observer, "_client") as mock_client:
            mock_client.post = AsyncMock()
            await filtered_observer.on_event(event)
            mock_client.post.assert_not_called()

    async def test_filter_allows_wanted(self, filtered_observer: WebhookObserver) -> None:
        """Events in the filter should be sent."""
        event = SyncCompleted(summary="done")
        with patch.object(filtered_observer, "_client") as mock_client:
            mock_client.post = AsyncMock()
            mock_client.post.return_value.raise_for_status = lambda: None
            await filtered_observer.on_event(event)
            mock_client.post.assert_called_once()

    async def test_filter_allows_resource_failed(self, filtered_observer: WebhookObserver) -> None:
        """ResourceFailed should be allowed (in filter list)."""
        event = ResourceFailed(resource_name="r1", error="err", stage="fetch")
        with patch.object(filtered_observer, "_client") as mock_client:
            mock_client.post = AsyncMock()
            mock_client.post.return_value.raise_for_status = lambda: None
            await filtered_observer.on_event(event)
            mock_client.post.assert_called_once()

    async def test_no_filter_sends_all(self, generic_observer: WebhookObserver) -> None:
        """Without a filter, all handled events should be sent."""
        event = ResourceSkipped(resource_name="r1")
        with patch.object(generic_observer, "_client") as mock_client:
            mock_client.post = AsyncMock()
            mock_client.post.return_value.raise_for_status = lambda: None
            await generic_observer.on_event(event)
            mock_client.post.assert_called_once()


class TestEventHandling:
    """Event handling and error scenarios on WebhookObserver."""

    async def test_unhandled_event_skipped(self, generic_observer: WebhookObserver) -> None:
        """Unhandled event types should not send a webhook."""
        # Intentionally imported here to avoid changing the test structure
        from resource_sync.domain.events import ResourceHashCompared

        event = ResourceHashCompared(resource_name="r1", matched=False)
        with patch.object(generic_observer, "_client") as mock_client:
            mock_client.post = AsyncMock()
            await generic_observer.on_event(event)
            mock_client.post.assert_not_called()

    async def test_http_error_logged(self, generic_observer: WebhookObserver) -> None:
        """HTTP errors should be logged, not propagated."""
        import httpx

        event = SyncCompleted(summary="done")
        with patch.object(generic_observer, "_client") as mock_client:
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed"),
            )
            # Should not raise
            await generic_observer.on_event(event)
            mock_client.post.assert_called_once()

    async def test_sync_started_payload(self, generic_observer: WebhookObserver) -> None:
        """SyncStarted event should produce a valid payload."""
        event = SyncStarted(config_summary="5 resources")
        # The platform impl is the one building the payload
        payload = generic_observer._platform_impl.build_payload(event)
        assert payload is not None
        assert "5 resources" in payload["message"]

    async def test_resource_skipped_payload(self, generic_observer: WebhookObserver) -> None:
        """ResourceSkipped event should produce a valid payload."""
        event = ResourceSkipped(resource_name="r1")
        payload = generic_observer._platform_impl.build_payload(event)
        assert payload is not None
        assert "r1" in payload["message"]


class TestConfigure:
    """WebhookObserver.configure() factory method."""

    def test_configure_minimal(self) -> None:
        """Minimal config should produce a valid observer."""
        observer = WebhookObserver.configure({
            "platform": "slack",
            "url": "https://hooks.slack.com/xxx",
        })
        assert observer._platform == "slack"
        assert observer._url == "https://hooks.slack.com/xxx"
        assert observer._secret == ""

    def test_configure_with_secret(self) -> None:
        """Config with secret should set the secret."""
        observer = WebhookObserver.configure({
            "platform": "dingtalk",
            "url": "https://oapi.dingtalk.com/robot/send?token=xxx",
            "secret": "my-secret-123",
        })
        assert observer._secret == "my-secret-123"

    def test_configure_with_event_filter(self) -> None:
        """Config with event filter should set the filter."""
        observer = WebhookObserver.configure({
            "platform": "generic",
            "url": "https://hooks.example.com",
            "events": ["SyncCompleted", "SyncStarted"],
        })
        assert observer._event_filter == ["SyncCompleted", "SyncStarted"]

    def test_configure_default_platform(self) -> None:
        """Default platform should be 'generic'."""
        observer = WebhookObserver.configure({
            "url": "https://hooks.example.com",
        })
        assert observer._platform == "generic"