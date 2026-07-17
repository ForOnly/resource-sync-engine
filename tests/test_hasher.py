"""Tests for ``resource_sync.hasher``."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from resource_sync.exceptions import HashError
from resource_sync.hasher import hash_bytes, hash_file
from resource_sync.models import HashAlgorithm, HashResult


class TestHashBytes:
    """Tests for ``hash_bytes``."""

    def test_sha256(self) -> None:
        """SHA-256 hex digest matches hashlib directly."""
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        result = hash_bytes(data, HashAlgorithm.SHA256)
        assert result.hex_digest == expected
        assert result.algorithm is HashAlgorithm.SHA256

    def test_sha1(self) -> None:
        """SHA-1 hex digest matches hashlib directly."""
        data = b"hello world"
        expected = hashlib.sha1(data).hexdigest()
        result = hash_bytes(data, HashAlgorithm.SHA1)
        assert result.hex_digest == expected

    def test_md5(self) -> None:
        """MD5 hex digest matches hashlib directly."""
        data = b"hello world"
        expected = hashlib.md5(data).hexdigest()
        result = hash_bytes(data, HashAlgorithm.MD5)
        assert result.hex_digest == expected

    def test_empty_bytes(self) -> None:
        """Empty bytes produce a valid hash."""
        result = hash_bytes(b"", HashAlgorithm.SHA256)
        assert isinstance(result.hex_digest, str)
        assert len(result.hex_digest) == 64  # SHA-256 hex length

    def test_large_data(self) -> None:
        """Large byte strings are hashed correctly."""
        data = b"a" * 10_000_000  # 10 MB
        expected = hashlib.sha256(data).hexdigest()
        result = hash_bytes(data, HashAlgorithm.SHA256)
        assert result.hex_digest == expected

    def test_return_type(self) -> None:
        """Returns a HashResult dataclass."""
        result = hash_bytes(b"test", HashAlgorithm.SHA256)
        assert isinstance(result, HashResult)
        assert isinstance(result.hex_digest, str)


class TestHashFile:
    """Tests for ``hash_file``."""

    def test_sha256(self, tmp_path: Path) -> None:
        """SHA-256 hash of a file matches hashlib directly."""
        file_path = tmp_path / "test.bin"
        data = b"hello world"
        file_path.write_bytes(data)

        expected = hashlib.sha256(data).hexdigest()
        result = hash_file(file_path, HashAlgorithm.SHA256)
        assert result.hex_digest == expected

    def test_large_file(self, tmp_path: Path) -> None:
        """Large files are hashed using streaming."""
        file_path = tmp_path / "large.bin"
        data = b"B" * 2_000_000  # 2 MB
        file_path.write_bytes(data)

        expected = hashlib.sha256(data).hexdigest()
        result = hash_file(file_path, HashAlgorithm.SHA256)
        assert result.hex_digest == expected

    def test_file_not_found(self) -> None:
        """Raises HashError for missing files."""
        with pytest.raises(HashError, match="not found"):
            hash_file(Path("/nonexistent/file.bin"))

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty files produce a valid hash."""
        file_path = tmp_path / "empty.bin"
        file_path.write_bytes(b"")

        expected = hashlib.sha256(b"").hexdigest()
        result = hash_file(file_path, HashAlgorithm.SHA256)
        assert result.hex_digest == expected

    def test_return_type(self, tmp_path: Path) -> None:
        """Returns a HashResult dataclass."""
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(b"data")

        result = hash_file(file_path, HashAlgorithm.SHA256)
        assert isinstance(result, HashResult)
        assert isinstance(result.hex_digest, str)
        assert isinstance(result.algorithm, HashAlgorithm)


class TestHashResultMatches:
    """Tests for ``HashResult.matches()``."""

    def test_identical(self) -> None:
        """Identical HashResults match."""
        a = HashResult(HashAlgorithm.SHA256, "abc123")
        b = HashResult(HashAlgorithm.SHA256, "abc123")
        assert a.matches(b)

    def test_different_digest(self) -> None:
        """Different digests do not match."""
        a = HashResult(HashAlgorithm.SHA256, "abc123")
        b = HashResult(HashAlgorithm.SHA256, "def456")
        assert not a.matches(b)

    def test_different_algorithm(self) -> None:
        """Different algorithms do not match (even if digest happens to match)."""
        a = HashResult(HashAlgorithm.SHA256, "abc123")
        b = HashResult(HashAlgorithm.SHA1, "abc123")
        assert not a.matches(b)


class TestHashResultStr:
    """Tests for ``HashResult.__str__``."""

    def test_format(self) -> None:
        """String representation includes algorithm and digest."""
        result = HashResult(HashAlgorithm.SHA256, "abc123")
        assert str(result) == "sha256:abc123"