"""Log observer — logs domain events to the standard logging system."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from resource_sync.domain.events import (
    Event, ResourceFailed, ResourceFetchCompleted, ResourceFetchStarted,
    ResourceSkipped, ResourceWritten, SyncCompleted, SyncStarted,
)

from resource_sync.plugin.registry import register_observer

_LOGGER = logging.getLogger(__name__)


@register_observer
class LogObserver:
    """Logs all domain events to Python's logging system."""
    name: ClassVar[str] = "log"

    @classmethod
    def configure(cls, config: dict[str, Any]) -> LogObserver:
        return cls()

    async def on_event(self, event: Event) -> None:
        t = type(event)
        if t is SyncStarted:
            _LOGGER.info("Sync started: %s", event.config_summary)
        elif t is SyncCompleted:
            _LOGGER.info("Sync completed: %s", event.summary)
        elif t is ResourceFetchStarted:
            _LOGGER.debug("Fetching: %s", event.resource_name)
        elif t is ResourceFetchCompleted:
            _LOGGER.debug("Fetched: %s (%d bytes)", event.resource_name, event.bytes_downloaded)
        elif t is ResourceWritten:
            _LOGGER.info("Written: %s → %s (%d bytes)", event.resource_name, event.path, event.bytes_written)
        elif t is ResourceSkipped:
            _LOGGER.info("Skipped: %s", event.resource_name)
        elif t is ResourceFailed:
            _LOGGER.error("Failed: %s (stage=%s): %s", event.resource_name, event.stage, event.error)