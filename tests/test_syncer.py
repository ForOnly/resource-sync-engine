"""Tests for ``resource_sync.syncer``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, patch

import pytest

from resource_sync.hasher import hash_bytes, hash_file
from resource_sync.models import HashAlgorithm, Resource, SyncConfig, SyncStatus
from resource_sync.syncer import sync_resources


@pytest.fixture
def single_resource(tmp_path: Path) -> tuple[SyncConfig, Path]:
    """Return a config with a single resource pointing to a temp path."""
    dest = tmp_path / "output" / "data.txt"
    resource = Resource(
        name="test-resource",
        url="https://example.com/data.txt",
        path=dest,
        algorithm=HashAlgorithm.SHA256,
    )
    config = SyncConfig(resources=(resource,))
    return config, tmp_path


@pytest.fixture
def multiple_resources(tmp_path: Path) -> SyncConfig:
    """Return a config with three resources."""
    resources = [
        Resource(
            name=f"resource-{i}",
            url=f"https://example.com/{i}.txt",
            path=tmp_path / f"output/{i}.txt",
            algorithm=HashAlgorithm.SHA256,
        )
        for i in range(3)
    ]
    return SyncConfig(resources=tuple(resources))


class TestSyncResources:
    """Tests for ``sync_resources``."""

    @patch("resource_sync.syncer.download_resource")
    def test_created_when_file_missing(
        self, mock_download, single_resource, tmp_path
    ) -> None:
        """A missing file is created (CREATED status)."""
        config, _ = single_resource
        mock_download.return_value = b"hello world"

        report = sync_resources(config, dry_run=False)
        result = report.results[0]

        assert result.status is SyncStatus.CREATED
        assert result.error_message is None
        # Verify the file was actually written
        dest = config.resources[0].path
        assert dest.exists()
        assert dest.read_bytes() == b"hello world"

    @patch("resource_sync.syncer.download_resource")
    def test_skipped_when_hash_matches(
        self, mock_download, single_resource, tmp_path
    ) -> None:
        """When hashes match, the resource is skipped."""
        config, _ = single_resource
        content = b"existing content"
        mock_download.return_value = content

        # Create the file first
        dest = config.resources[0].path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

        report = sync_resources(config, dry_run=False)
        result = report.results[0]

        assert result.status is SyncStatus.SKIPPED
        assert result.local_hash is not None
        assert result.remote_hash is not None
        assert result.local_hash.matches(result.remote_hash)

    @patch("resource_sync.syncer.download_resource")
    def test_updated_when_hash_differs(
        self, mock_download, single_resource, tmp_path
    ) -> None:
        """When hashes differ, the resource is updated."""
        config, _ = single_resource
        mock_download.return_value = b"new content"

        # Create file with different content
        dest = config.resources[0].path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"old content")

        report = sync_resources(config, dry_run=False)
        result = report.results[0]

        assert result.status is SyncStatus.UPDATED
        assert result.local_hash is not None
        assert result.remote_hash is not None
        assert not result.local_hash.matches(result.remote_hash)
        # Verify file content was updated
        assert dest.read_bytes() == b"new content"

    @patch("resource_sync.syncer.download_resource")
    def test_error_on_download_failure(
        self, mock_download, single_resource
    ) -> None:
        """A download failure produces ERROR status without crashing."""
        from resource_sync.exceptions import DownloadError

        config, _ = single_resource
        mock_download.side_effect = DownloadError("Connection refused")

        report = sync_resources(config, dry_run=False)
        result = report.results[0]

        assert result.status is SyncStatus.ERROR
        assert result.error_message is not None
        assert "Connection refused" in result.error_message

    @patch("resource_sync.syncer.download_resource")
    def test_dry_run_does_not_write_files(
        self, mock_download, single_resource, tmp_path
    ) -> None:
        """In dry-run mode, files are not written to disk."""
        config, _ = single_resource
        mock_download.return_value = b"hello world"

        report = sync_resources(config, dry_run=True)
        result = report.results[0]

        assert result.status is SyncStatus.CREATED
        assert result.dry_run is True
        # File should NOT exist
        dest = config.resources[0].path
        assert not dest.exists()

    @patch("resource_sync.syncer.download_resource")
    def test_dry_run_detects_hash_match(
        self, mock_download, single_resource, tmp_path
    ) -> None:
        """Dry-run correctly detects when hash would match."""
        config, _ = single_resource
        content = b"existing content"
        mock_download.return_value = content

        dest = config.resources[0].path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

        report = sync_resources(config, dry_run=True)
        result = report.results[0]

        assert result.status is SyncStatus.SKIPPED
        assert result.dry_run is True
        # File should still exist (unchanged)
        assert dest.exists()
        assert dest.read_bytes() == content

    @patch("resource_sync.syncer.download_resource")
    def test_dry_run_detects_hash_mismatch(
        self, mock_download, single_resource, tmp_path
    ) -> None:
        """Dry-run correctly detects when hash would differ without updating."""
        config, _ = single_resource
        mock_download.return_value = b"new content"

        dest = config.resources[0].path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"old content")

        report = sync_resources(config, dry_run=True)
        result = report.results[0]

        assert result.status is SyncStatus.UPDATED
        assert result.dry_run is True
        # File should NOT be updated
        assert dest.read_bytes() == b"old content"

    @patch("resource_sync.syncer.download_resource")
    def test_report_summary(
        self, mock_download, multiple_resources
    ) -> None:
        """Sync report provides correct summary counts."""
        config = multiple_resources

        # First resource: new (CREATED)
        # Second resource: match (SKIPPED) — need to create first
        # Third resource: error
        mock_download.side_effect = [
            b"new resource",
            b"existing resource",
        ]
        # Create the second resource's file to match
        res1 = config.resources[1]
        res1.path.parent.mkdir(parents=True, exist_ok=True)
        res1.path.write_bytes(b"existing resource")

        # Mock third download to fail
        # We need a way to make only the third fail. Let's restructure:
        # Actually mock_download.side_effect with 3 elements
        mock_download.reset_mock()
        from resource_sync.exceptions import DownloadError

        mock_download.side_effect = [
            b"new resource",
            b"existing resource",
            DownloadError("Server error"),
        ]

        report = sync_resources(config, dry_run=False)

        assert report.summary.get("created", 0) == 1
        assert report.summary.get("skipped", 0) == 1
        assert report.summary.get("error", 0) == 1
        assert report.summary.get("updated", 0) == 0
        assert report.changed == 1  # only created

    @patch("resource_sync.syncer.download_resource")
    def test_content_validation_called(
        self, mock_download, single_resource
    ) -> None:
        """Content validation is performed on downloaded data."""
        # This tests that content validation runs (and that HTML error page
        # detection can trigger ERROR). We'll mock it to validate behavior.
        config, _ = single_resource
        # Simulate an HTML error page being downloaded
        html_error = b"<html><head><title>404 Not Found</title></head><body>Not Found</body></html>"
        mock_download.return_value = html_error

        report = sync_resources(config, dry_run=False)
        result = report.results[0]

        # The content validator should catch this as an HTML error page
        assert result.status is SyncStatus.ERROR
        assert "HTML error page" in (result.error_message or "")

    @patch("resource_sync.syncer.download_resource")
    def test_all_resources_processed(
        self, mock_download, multiple_resources
    ) -> None:
        """All resources in the config are processed and appear in the report."""
        config = multiple_resources
        mock_download.return_value = b"content"

        report = sync_resources(config, dry_run=False)
        assert len(report.results) == 3
        names = [r.resource_name for r in report.results]
        assert "resource-0" in names
        assert "resource-1" in names
        assert "resource-2" in names

    @patch("resource_sync.syncer.download_resource")
    def test_report_serialization(self, mock_download, single_resource) -> None:
        """SyncReport.to_dict() and to_json() work correctly."""
        config, _ = single_resource
        mock_download.return_value = b"hello"

        report = sync_resources(config, dry_run=False)
        d = report.to_dict()
        assert "run_id" in d
        assert "timestamp" in d
        assert "summary" in d
        assert "results" in d
        assert len(d["results"]) == 1

        json_str = report.to_json()
        assert isinstance(json_str, str)
        assert report.to_dict()["run_id"] in json_str