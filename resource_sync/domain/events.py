"""Domain events — emitted by the pipeline at each stage, observers subscribe."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Event(BaseModel):
    """Base class for all domain events."""
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SyncStarted(Event):
    config_summary: str = ""


class SyncCompleted(Event):
    summary: str = ""


class ResourceFetchStarted(Event):
    resource_name: str = ""


class ResourceFetchCompleted(Event):
    resource_name: str = ""
    bytes_downloaded: int = 0


class ResourceFetchFailed(Event):
    resource_name: str = ""
    error: str = ""


class ResourceValidationPassed(Event):
    resource_name: str = ""
    validator: str = ""


class ResourceValidationFailed(Event):
    resource_name: str = ""
    validator: str = ""
    error: str = ""


class ResourceHashCompared(Event):
    resource_name: str = ""
    matched: bool = False


class ResourceWritten(Event):
    resource_name: str = ""
    path: str = ""
    bytes_written: int = 0


class ResourceSkipped(Event):
    resource_name: str = ""


class ResourceRemoteUnchanged(Event):
    """Emitted when the server returns 304 Not Modified (ETag/Last-Modified match)."""
    resource_name: str = ""


class ResourceFailed(Event):
    resource_name: str = ""
    error: str = ""
    stage: str = ""