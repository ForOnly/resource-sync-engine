"""Pure domain models — Pydantic-based immutable value objects."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HashAlgorithm(str, Enum):
    SHA256 = "sha256"
    SHA1 = "sha1"
    MD5 = "md5"


class SyncStatus(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"
    CANCELLED = "cancelled"


class HashResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    algorithm: HashAlgorithm
    hex_digest: str

    def matches(self, other: HashResult) -> bool:
        return self.algorithm is other.algorithm and self.hex_digest == other.hex_digest

    def __str__(self) -> str:
        return f"{self.algorithm.value}:{self.hex_digest}"


class Resource(BaseModel):
    """A single resource definition — pure data, no I/O."""
    model_config = ConfigDict(frozen=True)
    name: str
    url: str
    path: PurePath
    algorithm: HashAlgorithm = HashAlgorithm.SHA256
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float = 30.0
    retry: int = 3
    max_size: int = 524_288_000
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceResult(BaseModel):
    """Per-resource outcome of a single sync operation."""
    model_config = ConfigDict(frozen=True)
    resource_name: str
    status: SyncStatus
    local_hash: HashResult | None = None
    remote_hash: HashResult | None = None
    error_message: str | None = None
    stage_times: dict[str, float] = Field(default_factory=dict)
    dry_run: bool = False


class SyncReport(BaseModel):
    """Aggregate report for a full sync run."""
    model_config = ConfigDict(frozen=True)
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    dry_run: bool = False
    results: tuple[ResourceResult, ...] = ()

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        return counts

    @property
    def changed(self) -> int:
        return self.summary.get("created", 0) + self.summary.get("updated", 0)

    @property
    def has_errors(self) -> bool:
        return self.summary.get("error", 0) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "dry_run": self.dry_run,
            "summary": self.summary,
            "results": [
                {
                    "resource_name": r.resource_name,
                    "status": r.status.value,
                    "local_hash": str(r.local_hash) if r.local_hash else None,
                    "remote_hash": str(r.remote_hash) if r.remote_hash else None,
                    "error_message": r.error_message,
                    "dry_run": r.dry_run,
                }
                for r in self.results
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)