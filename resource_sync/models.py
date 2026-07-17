"""
Domain models — dataclasses and enums used across all modules.

All configuration models are frozen (immutable). Result models are mutable
because they are built incrementally during a sync run.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class HashAlgorithm(str, Enum):
    """Supported hash algorithms."""

    SHA256 = "sha256"
    SHA1 = "sha1"
    MD5 = "md5"


class SyncStatus(str, Enum):
    """Per-resource outcome of a sync operation."""

    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class Resource:
    """A single resource definition parsed from the YAML config."""

    name: str
    url: str
    path: Path
    algorithm: HashAlgorithm = HashAlgorithm.SHA256
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    retry: int = 3
    max_size: int = 500 * 1024 * 1024  # 500 MB


@dataclass(frozen=True)
class SyncConfig:
    """Top-level configuration holding all resources."""

    resources: tuple[Resource, ...]


@dataclass(frozen=True)
class HashResult:
    """Result of a hash computation — algorithm plus hex digest."""

    algorithm: HashAlgorithm
    hex_digest: str

    def matches(self, other: HashResult) -> bool:
        """Return ``True`` if both algorithm and digest are identical."""
        return self.algorithm is other.algorithm and self.hex_digest == other.hex_digest

    def __str__(self) -> str:
        return f"{self.algorithm.value}:{self.hex_digest}"


@dataclass
class SyncResult:
    """Per-resource outcome of a single sync operation."""

    resource_name: str
    status: SyncStatus
    local_hash: HashResult | None = None
    remote_hash: HashResult | None = None
    error_message: str | None = None
    dry_run: bool = False


@dataclass
class SyncReport:
    """Aggregate report for a full sync run, serializable to JSON."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    dry_run: bool = False
    results: list[SyncResult] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        """Return a count breakdown by status."""
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        return counts

    @property
    def changed(self) -> int:
        """Number of resources that were created or updated."""
        return self.summary.get("created", 0) + self.summary.get("updated", 0)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a JSON-compatible dictionary."""
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
        """Return the report as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)