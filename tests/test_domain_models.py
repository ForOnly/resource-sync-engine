"""Tests for domain models (Resource, SyncReport, ResourceResult, etc.)."""

from __future__ import annotations

from pathlib import PurePath

import pytest
from pydantic import ValidationError

from resource_sync.domain.models import (
    HashAlgorithm,
    HashResult,
    Resource,
    ResourceResult,
    SyncReport,
    SyncStatus,
)


class TestResource:
    """Resource model validation."""

    def test_valid_resource(self, sample_resource: Resource) -> None:
        assert sample_resource.name == "test-resource"
        assert sample_resource.url == "https://example.com/data.json"
        # path is a PurePath (PureWindowsPath on Windows — uses backslashes)
        assert isinstance(sample_resource.path, PurePath)
        assert PurePath("/tmp/test-resource.json") == sample_resource.path
        assert sample_resource.algorithm == HashAlgorithm.SHA256
        assert sample_resource.max_size == 1024 * 1024
        assert sample_resource.headers == {"Authorization": "Bearer test-token"}

    def test_default_algorithm(self) -> None:
        r = Resource(
            name="default-algo",
            url="https://example.com/f",
            path="/tmp/f",
        )
        assert r.algorithm == HashAlgorithm.SHA256

    def test_default_max_size(self) -> None:
        r = Resource(
            name="no-max-size",
            url="https://example.com/f",
            path="/tmp/f",
            algorithm=HashAlgorithm.SHA256,
        )
        # Default max_size is 524288000 (500MB) from the model definition
        assert r.max_size == 524_288_000

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            Resource()  # type: ignore[call-arg]

    def test_empty_name(self) -> None:
        """Empty name is allowed by the model (no min_length constraint)."""
        r = Resource(
            name="",
            url="https://example.com/f",
            path="/tmp/f",
            algorithm=HashAlgorithm.SHA256,
        )
        assert r.name == ""


class TestHashResult:
    """HashResult equality and matching."""

    def test_match_equal(self) -> None:
        h1 = HashResult(algorithm=HashAlgorithm.SHA256, hex_digest="abc")
        h2 = HashResult(algorithm=HashAlgorithm.SHA256, hex_digest="abc")
        assert h1.matches(h2)

    def test_no_match_different_digest(self) -> None:
        h1 = HashResult(algorithm=HashAlgorithm.SHA256, hex_digest="abc")
        h2 = HashResult(algorithm=HashAlgorithm.SHA256, hex_digest="def")
        assert not h1.matches(h2)

    def test_no_match_different_algorithm(self) -> None:
        h1 = HashResult(algorithm=HashAlgorithm.SHA256, hex_digest="abc")
        h2 = HashResult(algorithm=HashAlgorithm.SHA1, hex_digest="abc")
        assert not h1.matches(h2)

    def test_string_representation(self) -> None:
        h = HashResult(algorithm=HashAlgorithm.SHA256, hex_digest="abc123")
        assert "sha256" in str(h)
        assert "abc123" in str(h)


class TestSyncReport:
    """SyncReport creation and summary."""

    def test_empty_report(self) -> None:
        report = SyncReport(dry_run=False, results=())
        assert report.dry_run is False
        assert len(report.results) == 0
        assert report.run_id is not None
        assert report.timestamp is not None

    def test_summary_counts(self) -> None:
        results = (
            ResourceResult(
                resource_name="r1", status=SyncStatus.CREATED, local_hash=None, remote_hash=None,
            ),
            ResourceResult(
                resource_name="r2", status=SyncStatus.UPDATED, local_hash=None, remote_hash=None,
            ),
            ResourceResult(
                resource_name="r3", status=SyncStatus.SKIPPED, local_hash=None, remote_hash=None,
            ),
            ResourceResult(
                resource_name="r4", status=SyncStatus.ERROR, local_hash=None, remote_hash=None,
                error_message="Failed",
            ),
        )
        report = SyncReport(dry_run=False, results=results)
        summary = report.summary
        assert summary["created"] == 1
        assert summary["updated"] == 1
        assert summary["skipped"] == 1
        assert summary["error"] == 1

    def test_changed_property(self) -> None:
        results = (
            ResourceResult(
                resource_name="r1", status=SyncStatus.CREATED, local_hash=None, remote_hash=None,
            ),
            ResourceResult(
                resource_name="r2", status=SyncStatus.UPDATED, local_hash=None, remote_hash=None,
            ),
            ResourceResult(
                resource_name="r3", status=SyncStatus.SKIPPED, local_hash=None, remote_hash=None,
            ),
        )
        report = SyncReport(dry_run=False, results=results)
        assert report.changed == 2  # created + updated

    def test_to_dict_includes_stage_times(self) -> None:
        results = (
            ResourceResult(
                resource_name="r1",
                status=SyncStatus.CREATED,
                local_hash=None,
                remote_hash=None,
                stage_times={"fetch": 100.0, "sink": 50.0},
            ),
        )
        report = SyncReport(dry_run=False, results=results)
        d = report.to_dict()
        assert d["results"][0]["stage_times_ms"] == {"fetch": 100.0, "sink": 50.0}


class TestResourceResult:
    """ResourceResult validation."""

    def test_error_result(self) -> None:
        result = ResourceResult(
            resource_name="r1",
            status=SyncStatus.ERROR,
            error_message="Connection timeout",
        )
        assert result.status == SyncStatus.ERROR
        assert result.error_message == "Connection timeout"

    def test_created_result(self) -> None:
        result = ResourceResult(
            resource_name="r1",
            status=SyncStatus.CREATED,
            local_hash=None,
            remote_hash=HashResult(
                algorithm=HashAlgorithm.SHA256, hex_digest="abc123",
            ),
        )
        assert result.status == SyncStatus.CREATED
        assert result.remote_hash is not None
        assert result.local_hash is None