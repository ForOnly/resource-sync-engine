"""Tests for ``resource_sync.cli``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from resource_sync.cli import build_parser, main


class TestBuildParser:
    """Tests for the argument parser."""

    def test_default_config_path(self) -> None:
        """Default config path is config.yaml."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.config == Path("config.yaml")

    def test_dry_run_flag(self) -> None:
        """--dry-run sets dry_run to True."""
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_no_dry_run_by_default(self) -> None:
        """dry_run is False by default."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.dry_run is False

    def test_no_commit_flag(self) -> None:
        """--no-commit sets no_commit to True."""
        parser = build_parser()
        args = parser.parse_args(["--no-commit"])
        assert args.no_commit is True

    def test_custom_config(self) -> None:
        """-c sets a custom config path."""
        parser = build_parser()
        args = parser.parse_args(["-c", "my-config.yaml"])
        assert args.config == Path("my-config.yaml")

    def test_verbose_flag(self) -> None:
        """-v sets verbose to True."""
        parser = build_parser()
        args = parser.parse_args(["-v"])
        assert args.verbose is True

    def test_repo_root(self) -> None:
        """--repo-root sets a custom repo root."""
        parser = build_parser()
        args = parser.parse_args(["--repo-root", "/custom/repo"])
        assert args.repo_root == Path("/custom/repo")


class TestMain:
    """Tests for the ``main`` entry point."""

    @patch("resource_sync.cli.load_config")
    @patch("resource_sync.cli.sync_resources")
    @patch("resource_sync.cli.auto_commit_and_push")
    def test_successful_run(
        self,
        mock_git,
        mock_sync,
        mock_config,
        tmp_path: Path,
    ) -> None:
        """A successful sync run returns 0."""
        from resource_sync.models import SyncReport, SyncStatus

        mock_config.return_value = None  # Just needs to not raise

        report = SyncReport()
        report.results.append(
            type("Result", (), {"resource_name": "test", "status": SyncStatus.CREATED, "dry_run": False})()  # type: ignore
        )
        mock_sync.return_value = report

        config_path = tmp_path / "config.yaml"
        config_path.write_text("resources: []")

        exit_code = main(["-c", str(config_path), "--no-commit", "--repo-root", str(tmp_path)])
        assert exit_code == 0

    @patch("resource_sync.cli.load_config")
    @patch("resource_sync.cli.sync_resources")
    @patch("resource_sync.cli.auto_commit_and_push")
    def test_run_with_errors_returns_1(
        self,
        mock_git,
        mock_sync,
        mock_config,
        tmp_path: Path,
    ) -> None:
        """A sync with errors returns 1."""
        from resource_sync.models import SyncReport, SyncStatus

        mock_config.return_value = None

        report = SyncReport()
        report.results.append(
            type("Result", (), {"resource_name": "test", "status": SyncStatus.ERROR, "error_message": "Failed", "dry_run": False})()  # type: ignore
        )
        mock_sync.return_value = report

        config_path = tmp_path / "config.yaml"
        config_path.write_text("resources: []")

        exit_code = main(["-c", str(config_path), "--no-commit", "--repo-root", str(tmp_path)])
        assert exit_code == 1

    @patch("resource_sync.cli.load_config")
    @patch("resource_sync.cli.sync_resources")
    @patch("resource_sync.cli.auto_commit_and_push")
    def test_dry_run_does_not_commit(
        self,
        mock_git,
        mock_sync,
        mock_config,
        tmp_path: Path,
    ) -> None:
        """Dry-run mode skips git commit."""
        from resource_sync.models import SyncReport, SyncStatus

        mock_config.return_value = None

        report = SyncReport(dry_run=True)
        report.results.append(
            type("Result", (), {"resource_name": "test", "status": SyncStatus.CREATED, "dry_run": True})()  # type: ignore
        )
        mock_sync.return_value = report

        config_path = tmp_path / "config.yaml"
        config_path.write_text("resources: []")

        exit_code = main(["-c", str(config_path), "--dry-run", "--repo-root", str(tmp_path)])
        assert exit_code == 0
        mock_git.assert_not_called()

    @patch("resource_sync.cli.load_config")
    @patch("resource_sync.cli.sync_resources")
    @patch("resource_sync.cli.auto_commit_and_push")
    def test_no_commit_flag_skips_git(
        self,
        mock_git,
        mock_sync,
        mock_config,
        tmp_path: Path,
    ) -> None:
        """--no-commit skips git operations."""
        from resource_sync.models import SyncReport, SyncStatus

        mock_config.return_value = None

        report = SyncReport()
        report.results.append(
            type("Result", (), {"resource_name": "test", "status": SyncStatus.CREATED, "dry_run": False})()  # type: ignore
        )
        mock_sync.return_value = report

        config_path = tmp_path / "config.yaml"
        config_path.write_text("resources: []")

        exit_code = main(["-c", str(config_path), "--no-commit", "--repo-root", str(tmp_path)])
        assert exit_code == 0
        mock_git.assert_not_called()

    @patch("resource_sync.cli.load_config")
    def test_config_error_returns_1(
        self,
        mock_config,
        tmp_path: Path,
    ) -> None:
        """A ConfigError returns 1."""
        from resource_sync.exceptions import ConfigError

        mock_config.side_effect = ConfigError("Config file not found")

        config_path = tmp_path / "config.yaml"
        config_path.write_text("resources: []")

        exit_code = main(["-c", str(config_path), "--no-commit", "--repo-root", str(tmp_path)])
        assert exit_code == 1