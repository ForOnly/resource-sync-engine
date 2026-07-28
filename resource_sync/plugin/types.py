"""Plugin type definitions for documentation and type checking.

Actual registration is done via decorators in registry.py.
"""

from __future__ import annotations

from typing import Any, ClassVar, Protocol

from resource_sync.domain.events import Event
from resource_sync.domain.models import Resource
from resource_sync.domain.stream import StreamSink, StreamSource, StreamTransformer


class FetcherPlugin(Protocol):
    """Factory protocol for data-source plugins."""

    @classmethod
    def configure(cls, resource: Resource) -> StreamSource: ...


class TransformPlugin(Protocol):
    """Stream transform plugin protocol."""

    name: ClassVar[str]
    priority: ClassVar[int]

    @classmethod
    def should_apply(cls, resource: Resource) -> bool: ...

    def __call__(self) -> StreamTransformer: ...


class ValidatorPlugin(Protocol):
    """Content validation plugin protocol."""

    name: ClassVar[str]
    priority: ClassVar[int]

    @classmethod
    def should_apply(cls, resource: Resource) -> bool: ...

    def __call__(self) -> StreamTransformer: ...


class SinkPlugin(Protocol):
    """Output sink plugin protocol."""

    name: ClassVar[str]

    @classmethod
    def configure(cls, resource: Resource) -> StreamSink: ...


class EventObserver(Protocol):
    """Runtime observer receiving domain events."""

    async def on_event(self, event: Event) -> None: ...


class ObserverPlugin(Protocol):
    """Factory protocol for event observers."""

    name: ClassVar[str]

    @classmethod
    def configure(cls, config: dict[str, Any]) -> EventObserver: ...