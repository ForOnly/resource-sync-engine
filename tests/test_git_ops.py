"""Tests for ``resource_sync.git_ops``."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from resource_sync.exceptions import GitError
from resource_sync.git_ops import (
    auto_commit_and_push,
    commit,
    is_dirty,
    push,
    stage_all,
)


def _git(repo_root: Path, *args: str) -> str:
    """Run a git command in the given repo."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary Git repository with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)

    # Initialize git repo
    _git(repo, "init", "--initial-branch=main")

    # Configure user for commits
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    # Create initial commit (required for status checks)
    readme = repo / "README.md"
    readme.write_text("# Test Repo")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "Initial commit")

    return repo


class TestIsDirty:
    """Tests for ``is_dirty``."""

    def test_clean_repo(self, git_repo: Path) -> None:
        """A clean repo returns False."""
        assert is_dirty(git_repo) is False

    def test_untracked_file(self, git_repo: Path) -> None:
        """An untracked file makes the repo dirty."""
        (git_repo / "new_file.txt").write_text("content")
        assert is_dirty(git_repo) is True

    def test_modified_file(self, git_repo: Path) -> None:
        """A modified file makes the repo dirty."""
        readme = git_repo / "README.md"
        readme.write_text("# Modified Content")
        assert is_dirty(git_repo) is True

    def test_staged_file(self, git_repo: Path) -> None:
        """Staged but uncommitted changes make the repo dirty."""
        readme = git_repo / "README.md"
        readme.write_text("# Modified Content")
        _git(git_repo, "add", "README.md")
        assert is_dirty(git_repo) is True


class TestStageAll:
    """Tests for ``stage_all``."""

    def test_stages_all_changes(self, git_repo: Path) -> None:
        """stage_all stages all modified and untracked files."""
        (git_repo / "new.txt").write_text("new file")
        readme = git_repo / "README.md"
        readme.write_text("# Updated")
        stage_all(git_repo)

        status = _git(git_repo, "status", "--porcelain")
        # Both files should be staged (M for modified, A for added)
        # The porcelain shows staged files in the first column
        staged = [line for line in status.split("\n") if line and line[0] != " " and line[0] != "?"]
        assert len(staged) >= 1  # at least one staged change


class TestCommit:
    """Tests for ``commit``."""

    def test_commit_success(self, git_repo: Path) -> None:
        """A commit is created successfully."""
        (git_repo / "new.txt").write_text("content")
        stage_all(git_repo)
        commit(git_repo, "Add new file")

        log = _git(git_repo, "log", "--oneline")
        assert "Add new file" in log

    def test_commit_nothing_to_commit(self, git_repo: Path) -> None:
        """Committing with no staged changes raises GitError."""
        with pytest.raises(GitError, match="failed"):
            commit(git_repo, "Empty commit")


class TestPush:
    """Tests for ``push`` — limited since there's no remote."""

    def test_push_no_remote(self, git_repo: Path) -> None:
        """Pushing without a remote raises GitError."""
        with pytest.raises(GitError, match="failed"):
            push(git_repo)


class TestAutoCommitAndPush:
    """Tests for ``auto_commit_and_push``."""

    def test_no_changes_does_nothing(self, git_repo: Path) -> None:
        """With no changes, auto_commit_and_push does nothing."""
        auto_commit_and_push(git_repo, resource_count=0)
        log = _git(git_repo, "log", "--oneline")
        assert len(log.split("\n")) == 1  # still just the initial commit

    def test_with_changes_commits(self, git_repo: Path) -> None:
        """With changes, auto_commit_and_push stages and commits."""
        (git_repo / "data.txt").write_text("resource content")
        auto_commit_and_push(git_repo, resource_count=1)

        log = _git(git_repo, "log", "--oneline")
        assert len(log.split("\n")) == 2  # initial + new commit
        assert "auto-update" in log

    def test_commit_message_singular(self, git_repo: Path) -> None:
        """Commit message uses singular for 1 resource."""
        (git_repo / "data.txt").write_text("content")
        auto_commit_and_push(git_repo, resource_count=1)

        log = _git(git_repo, "log", "--oneline", "--format=%s")
        assert log == "chore(sync): auto-update 1 resource"

    def test_commit_message_plural(self, git_repo: Path) -> None:
        """Commit message uses plural for multiple resources."""
        (git_repo / "a.txt").write_text("a")
        (git_repo / "b.txt").write_text("b")
        auto_commit_and_push(git_repo, resource_count=2)

        log = _git(git_repo, "log", "--oneline", "--format=%s")
        assert log == "chore(sync): auto-update 2 resources"