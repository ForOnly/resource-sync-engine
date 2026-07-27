"""Tests for the in-memory event bus."""

from __future__ import annotations

import pytest

from resource_sync.domain.events import (
    Event,
    ResourceFetchCompleted,
    ResourceFetchStarted,
    ResourceWritten,
    SyncCompleted,
    SyncStarted,
)
from resource_sync.eventbus.memory import EventBus


class TestEventBus:
    """EventBus — subscribe and emit."""

    @pytest.mark.asyncio
    async def test_emit_and_subscribe(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe_handler(SyncStarted, handler)
        event = SyncStarted(config_summary="test")
        await bus.emit(event)
        assert len(received) == 1
        assert received[0] is event

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        bus = EventBus()
        received1: list[Event] = []
        received2: list[Event] = []

        async def handler1(event: Event) -> None:
            received1.append(event)

        async def handler2(event: Event) -> None:
            received2.append(event)

        bus.subscribe_handler(SyncStarted, handler1)
        bus.subscribe_handler(SyncStarted, handler2)
        await bus.emit(SyncStarted(config_summary="test"))
        assert len(received1) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe_handler(SyncStarted, handler)
        bus.unsubscribe(SyncStarted, handler)
        await bus.emit(SyncStarted(config_summary="test"))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_no_subscriber(self) -> None:
        """Emitting an event with no subscribers should not raise."""
        bus = EventBus()
        await bus.emit(SyncStarted(config_summary="test"))

    @pytest.mark.asyncio
    async def test_multiple_event_types(self) -> None:
        bus = EventBus()
        started: list[Event] = []
        completed: list[Event] = []

        async def on_started(event: Event) -> None:
            started.append(event)

        async def on_completed(event: Event) -> None:
            completed.append(event)

        bus.subscribe_handler(SyncStarted, on_started)
        bus.subscribe_handler(SyncCompleted, on_completed)

        await bus.emit(SyncStarted(config_summary="start"))
        await bus.emit(SyncCompleted(summary="done"))

        assert len(started) == 1
        assert len(completed) == 1


class TestDomainEvents:
    """Domain event creation."""

    def test_sync_started(self) -> None:
        event = SyncStarted(config_summary="test")
        assert event.config_summary == "test"

    def test_sync_completed(self) -> None:
        event = SyncCompleted(summary="done")
        assert event.summary == "done"

    def test_resource_fetch_started(self) -> None:
        event = ResourceFetchStarted(resource_name="r1")
        assert event.resource_name == "r1"

    def test_resource_fetch_completed(self) -> None:
        event = ResourceFetchCompleted(resource_name="r1", bytes_downloaded=1000)
        assert event.bytes_downloaded == 1000

    def test_resource_written(self) -> None:
        event = ResourceWritten(resource_name="r1", path="/tmp/f", bytes_written=500)
        assert event.bytes_written == 500