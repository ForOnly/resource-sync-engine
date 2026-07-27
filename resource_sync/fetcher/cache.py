"""Filesystem-backed ETag/Last-Modified cache for conditional HTTP requests.

Stores a JSON mapping of URL -> {etag, last_modified} in a file
named .resource-cache.json within the repo root.

The cache file is written atomically (temp file + rename) to prevent
corruption from concurrent runs. Missing or corrupted cache files
are silently handled as an empty cache.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

_CACHE_FILENAME = ".resource-cache.json"


@dataclass
class EtagInfo:
    """Cached ETag and/or Last-Modified value for a single URL."""
    etag: str | None = None
    last_modified: str | None = None

    def as_dict(self) -> dict[str, str]:
        d: dict[str, str] = {}
        if self.etag is not None:
            d["etag"] = self.etag
        if self.last_modified is not None:
            d["last_modified"] = self.last_modified
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EtagInfo:
        return cls(
            etag=str(data["etag"]) if "etag" in data else None,
            last_modified=str(data["last_modified"]) if "last_modified" in data else None,
        )


class EtagCache:
    """Persistent cache for ETag and Last-Modified values.

    Thread-safe for concurrent reads via a read-through cache pattern.
    The file is written only on explicit save() calls, not on every get/set.
    """

    def __init__(self, cache_dir: str | Path) -> None:
        self._cache_path = Path(cache_dir) / _CACHE_FILENAME
        self._data: dict[str, dict[str, str]] = {}
        self._dirty = False
        self._load()

    # ─── Public API ───

    def get(self, url: str) -> EtagInfo | None:
        """Look up cached ETag/Last-Modified for a URL.

        Returns None if the URL is not cached.
        """
        entry = self._data.get(url)
        if entry is None:
            return None
        return EtagInfo.from_dict(entry)

    def set(self, url: str, info: EtagInfo) -> None:
        """Cache ETag/Last-Modified for a URL.

        Does NOT write to disk immediately. Call save() to persist.
        """
        self._data[url] = info.as_dict()
        self._dirty = True

    def save(self) -> None:
        """Flush the cache to disk atomically.

        If the cache is unchanged since the last save, this is a no-op.
        """
        if not self._dirty:
            return
        self._save()
        self._dirty = False

    # ─── Internal ───

    def _load(self) -> None:
        """Load the cache from disk. Missing or corrupted files are silent."""
        if not self._cache_path.exists():
            _LOGGER.debug("No ETag cache file at '%s' — starting fresh", self._cache_path)
            return

        try:
            raw = self._cache_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                self._data = parsed
                _LOGGER.debug("Loaded ETag cache with %d entries from '%s'", len(self._data), self._cache_path)
            else:
                _LOGGER.warning("ETag cache file is not a dict — resetting")
        except (json.JSONDecodeError, OSError) as e:
            _LOGGER.warning("Failed to read ETag cache '%s': %s — starting fresh", self._cache_path, e)

    def _save(self) -> None:
        """Write the cache to disk atomically.

        Uses tempfile + os.replace to avoid partial writes corrupting
        the cache file.
        """
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self._cache_path.parent),
                prefix=f".{_CACHE_FILENAME}.",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(tmp_path_str, str(self._cache_path))
            _LOGGER.debug("Saved ETag cache with %d entries to '%s'", len(self._data), self._cache_path)
        except OSError as e:
            _LOGGER.error("Failed to save ETag cache '%s': %s", self._cache_path, e)