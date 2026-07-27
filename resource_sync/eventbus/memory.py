"""In-memory event bus — synchronous broadcast to all observers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from resource_sync.domain.events import Event

_LOGGER = logging.getLogger(__name__)
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Synchronous in-memory event bus. Observers subscribe to event types."""

    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = {}
        self._wildcards: list[EventHandler] = []

    def subscribe(self, event_type: type[Event] | None = None) -> Callable[[EventHandler], EventHandler]:
        """Decorator: subscribe a handler to an event type.

        Usage:
            @bus.subscribe(SyncStarted)
            async def handler(event): ...

        For direct (non-decorator) subscription, use subscribe_handler().
        """
        def decorator(handler: EventHandler) -> EventHandler:
            if event_type is None:
                self._wildcards.append(handler)
            else:
                self._handlers.setdefault(event_type, []).append(handler)
            return handler
        return decorator

    def subscribe_handler(self, event_type: type[Event], handler: EventHandler) -> None:
        """Directly subscribe a handler to an event type (non-decorator)."""
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Remove a handler from an event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def register_observer(self, observer: Any) -> None:
        if not hasattr(observer, "on_event"):
            return
        async def handler(event: Event) -> None:
            await observer.on_event(event)
        self._wildcards.append(handler)

    async def emit(self, event: Event) -> None:
        for handler in self._handlers.get(type(event), []):
            try:
                await handler(event)
            except Exception:
                _LOGGER.exception("Handler failed for %s", type(event).__name__)
        for handler in self._wildcards:
            try:
                await handler(event)
            except Exception:
                _LOGGER.exception("Wildcard handler failed for %s", type(event).__name__)