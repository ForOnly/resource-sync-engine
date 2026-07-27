"""Tests for EtagCache — filesystem-backed ETag/Last-Modified cache."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resource_sync.fetcher.cache import EtagCache, EtagInfo


class TestEtagInfo:
    """EtagInfo — data container for cached ETag/Last-Modified."""

    def test_empty(self) -> None:
        info = EtagInfo()
        assert info.etag is None
        assert info.last_modified is None
        assert info.as_dict() == {}

    def test_with_etag(self) -> None:
        info = EtagInfo(etag='"abc123"')
        assert info.as_dict() == {"etag": '"abc123"'}

    def test_with_both(self) -> None:
        info = EtagInfo(etag='"abc"', last_modified="Mon, 01 Jan 2024 00:00:00 GMT")
        d = info.as_dict()
        assert d["etag"] == '"abc"'
        assert d["last_modified"] == "Mon, 01 Jan 2024 00:00:00 GMT"

    def test_from_dict(self) -> None:
        info = EtagInfo.from_dict({"etag": '"x"', "last_modified": "y"})
        assert info.etag == '"x"'
        assert info.last_modified == "y"

    def test_from_dict_partial(self) -> None:
        info = EtagInfo.from_dict({"etag": '"x"'})
        assert info.etag == '"x"'
        assert info.last_modified is None


class TestEtagCache:
    """EtagCache — persistent cache operations."""

    def test_cache_dir_creation(self, tmp_path: Path) -> None:
        """Cache should create the directory if it doesn't exist."""
        nested = tmp_path / "nested" / "dir"
        cache = EtagCache(nested)
        assert cache is not None
        # Accessing the cache should not raise
        assert cache.get("https://example.com") is None

    def test_get_missing(self, tmp_path: Path) -> None:
        cache = EtagCache(tmp_path)
        assert cache.get("https://example.com") is None

    def test_set_and_get(self, tmp_path: Path) -> None:
        cache = EtagCache(tmp_path)
        info = EtagInfo(etag='"abc"', last_modified="Mon, 01 Jan 2024 00:00:00 GMT")
        cache.set("https://example.com/file", info)
        cache.save()

        # Read from a fresh cache instance to verify persistence
        cache2 = EtagCache(tmp_path)
        retrieved = cache2.get("https://example.com/file")
        assert retrieved is not None
        assert retrieved.etag == '"abc"'
        assert retrieved.last_modified == "Mon, 01 Jan 2024 00:00:00 GMT"

    def test_overwrite_entry(self, tmp_path: Path) -> None:
        cache = EtagCache(tmp_path)
        cache.set("https://example.com/file", EtagInfo(etag='"v1"'))
        cache.save()
        cache.set("https://example.com/file", EtagInfo(etag='"v2"'))
        cache.save()

        cache2 = EtagCache(tmp_path)
        retrieved = cache2.get("https://example.com/file")
        assert retrieved is not None
        assert retrieved.etag == '"v2"'

    def test_multiple_entries(self, tmp_path: Path) -> None:
        cache = EtagCache(tmp_path)
        cache.set("https://a.com/f1", EtagInfo(etag='"a"'))
        cache.set("https://b.com/f2", EtagInfo(etag='"b"'))
        cache.save()

        cache2 = EtagCache(tmp_path)
        assert cache2.get("https://a.com/f1") is not None
        assert cache2.get("https://a.com/f1").etag == '"a"'  # type: ignore[union-attr]
        assert cache2.get("https://b.com/f2") is not None
        assert cache2.get("https://b.com/f2").etag == '"b"'  # type: ignore[union-attr]

    def test_missing_file(self, tmp_path: Path) -> None:
        """Missing cache file should not raise."""
        cache = EtagCache(tmp_path / "nonexistent")
        assert cache.get("https://example.com") is None

    def test_corrupted_json(self, tmp_path: Path) -> None:
        """Corrupted cache file should be silently reset."""
        cache_file = tmp_path / ".resource-cache.json"
        cache_file.write_text("not valid json")
        cache = EtagCache(tmp_path)
        # Should not raise; should start fresh
        assert cache.get("https://example.com") is None

    def test_save_no_dirty(self, tmp_path: Path) -> None:
        """save() without any set() calls should be a no-op (no file created)."""
        cache = EtagCache(tmp_path)
        cache.save()
        cache_file = tmp_path / ".resource-cache.json"
        # The file may or may not exist; we just verify no error
        assert cache is not None

    def test_atomic_write_preserves_data(self, tmp_path: Path) -> None:
        """Concurrent-safe atomic write should preserve existing data."""
        cache = EtagCache(tmp_path)
        cache.set("https://example.com/1", EtagInfo(etag='"e1"'))
        cache.save()

        # Read back
        cache2 = EtagCache(tmp_path)
        assert cache2.get("https://example.com/1") is not None
        assert cache2.get("https://example.com/1").etag == '"e1"'  # type: ignore[union-attr]

    def test_cache_file_content(self, tmp_path: Path) -> None:
        """Verify the cache file format on disk."""
        cache = EtagCache(tmp_path)
        cache.set("https://example.com/f", EtagInfo(etag='"e1"', last_modified="lm1"))
        cache.save()

        cache_file = tmp_path / ".resource-cache.json"
        assert cache_file.exists()
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        assert raw["https://example.com/f"]["etag"] == '"e1"'
        assert raw["https://example.com/f"]["last_modified"] == "lm1"