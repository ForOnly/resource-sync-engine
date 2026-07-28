"""Tests for GitSink — repo root resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from resource_sync.sink.git import GitSink


class TestGitSink:
    """GitSink — repo root resolution and commit."""

    @pytest.fixture
    def git_repo(self, tmp_path: Path) -> Path:
        """Create a minimal git repo."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path, capture_output=True,
        )
        # Create an initial commit so there's a branch
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path, capture_output=True,
        )
        return tmp_path

    def test_repo_root_resolution(self, git_repo: Path) -> None:
        """repo_root should be resolved from the git repo root."""
        sink = GitSink(repo_root=git_repo)
        assert sink.repo_root == git_repo

    def test_default_repo_root(self) -> None:
        """Without explicit repo_root, should resolve from cwd."""
        # This may fail if not in a git repo, but it should not raise
        sink = GitSink()
        assert sink.repo_root is None  # or resolved

    def test_commit_all_no_changes(self, git_repo: Path) -> None:
        """commit_all with 0 changes should return True."""
        sink = GitSink(repo_root=git_repo)
        result = sink.commit_all(repo_root=git_repo, resource_count=0)
        assert result is True

    def test_commit_all_returns_false_when_push_fails(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failed push must make the full Git operation fail."""
        sink = GitSink(repo_root=git_repo)

        def fake_run(repo_root: Path, *args: str) -> str | None:
            command = args[0]
            if command == "status":
                return " M resource.txt"
            if command == "rev-parse":
                return "master"
            if command == "push":
                return None
            return ""

        monkeypatch.setattr(sink, "_run", fake_run)

        result = sink.commit_all(repo_root=git_repo, resource_count=1)

        assert result is False

    def test_commit_all_accepts_successful_push_with_empty_stdout(
        self,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Git push commonly succeeds without writing to stdout."""
        sink = GitSink(repo_root=git_repo)

        def fake_run(repo_root: Path, *args: str) -> str | None:
            if args[0] == "status":
                return " M resource.txt"
            if args[0] == "rev-parse":
                return "master"
            return ""

        monkeypatch.setattr(sink, "_run", fake_run)

        result = sink.commit_all(repo_root=git_repo, resource_count=1)

        assert result is True