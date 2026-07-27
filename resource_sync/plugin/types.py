"""Plugin type definitions for documentation and type checking.

Actual registration is done via decorators in registry.py.
"""

from __future__ import annotations

from typing import Any, Protocol

from resource_sync.domain.stream import (
    StreamSink, StreamSource, StreamTransformer,
    PipelineContext, FetchResult, WriteResult, Stream,
)
from resource_sync.domain.models import Resource
from resource_sync.domain.events import Event


class FetcherPlugin(Protocol):
    """Data source plugin protocol.

    A fetcher must implement:
    - supported_schemes: frozenset of URL schemes (e.g., {'http', 'https'})
    - configure(cls, resource) -> StreamSource: factory method
    """
    ...


class TransformPlugin(Protocol):
    """Stream transform plugin protocol."""
    ...


class ValidatorPlugin(Protocol):
    """Content validation plugin protocol."""
    ...


class SinkPlugin(Protocol):
    """Output sink plugin protocol."""
    ...


class ObserverPlugin(Protocol):
    """Observer plugin protocol — listens to events."""
    ...