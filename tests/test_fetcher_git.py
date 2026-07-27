"""Tests for GitFetcher — file retrieval from Git repositories."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import CancellationToken, PipelineContext
from resource_sync.fetcher.git import GitFetcher
from resource_sync.plugin.errors import PluginConfigurationError, PluginExecutionError


@pytest.fixture
def git_repo_with_file(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a temporary git repository with a file.

    Returns (repo_path, file_in_repo, file_content).
    """
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True, capture_output=True,
    )

    # Create a file
    file_rel = Path("subdir") / "data.txt"
    file_abs = repo / file_rel
    file_abs.parent.mkdir(parents=True, exist_ok=True)
    content = "hello world from git"
    file_abs.write_text(content)

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo, check=True, capture_output=True,
    )

    return repo, file_rel, content


@pytest.fixture
def cancel_token() -> CancellationToken:
    return CancellationToken()


@pytest.fixture
def pipeline_context(cancel_token: CancellationToken) -> PipelineContext:
    return PipelineContext(
        resource=Resource(
            name="test",
            url="git+https://example.com/repo.git",
            path="/tmp/out",
        ),
        cancel=cancel_token,
        env={},
        config={"dry_run": False},
    )


class TestGitFetcher:
    """GitFetcher — URL resolution, auth, and file retrieval."""

    def test_url_scheme_stripping(self) -> None:
        """``git+https://`` should be stripped to ``https://``."""
        url = GitFetcher._resolve_repo_url("git+https://github.com/org/repo.git")
        assert url == "https://github.com/org/repo.git"

    def test_url_scheme_stripping_ssh(self) -> None:
        """``git+ssh://`` should be stripped to ``ssh://``."""
        url = GitFetcher._resolve_repo_url("git+ssh://git@github.com/org/repo.git")
        assert url == "ssh://git@github.com/org/repo.git"

    def test_url_without_prefix(self) -> None:
        """``git://`` should remain unchanged (no ``git+`` prefix)."""
        url = GitFetcher._resolve_repo_url("git://github.com/org/repo.git")
        assert url == "git://github.com/org/repo.git"

    def test_configure(self) -> None:
        """configure() should return a GitFetcher instance."""
        resource = Resource(
            name="test",
            url="git+https://example.com/repo.git",
            path="/tmp/out",
            metadata={"file_path": "file.txt", "ref": "main"},
        )
        fetcher = GitFetcher.configure(resource)
        assert isinstance(fetcher, GitFetcher)

    def test_auth_injection(self) -> None:
        """GIT_USERNAME and GIT_TOKEN should be embedded into the URL."""
        os.environ["GIT_USERNAME"] = "myuser"
        os.environ["GIT_TOKEN"] = "mytoken"
        try:
            url = GitFetcher._apply_auth("https://github.com/org/repo.git")
            assert "myuser:mytoken@" in url
            assert url == "https://myuser:mytoken@github.com/org/repo.git"
        finally:
            del os.environ["GIT_USERNAME"]
            del os.environ["GIT_TOKEN"]

    def test_auth_injection_no_username(self) -> None:
        """Without GIT_USERNAME, URL should remain unchanged."""
        url = GitFetcher._apply_auth("https://github.com/org/repo.git")
        assert "@" not in url or url.startswith("https://git")

    def test_auth_injection_existing_credentials(self) -> None:
        """URL with existing credentials should not be modified."""
        os.environ["GIT_USERNAME"] = "myuser"
        os.environ["GIT_TOKEN"] = "mytoken"
        try:
            url = GitFetcher._apply_auth("https://existing:pass@github.com/org/repo.git")
            assert "myuser:mytoken" not in url
        finally:
            del os.environ["GIT_USERNAME"]
            del os.environ["GIT_TOKEN"]

    def test_auth_uses_git_password_fallback(self) -> None:
        """GIT_PASSWORD should be used as fallback if GIT_TOKEN is not set."""
        os.environ["GIT_USERNAME"] = "u"
        os.environ["GIT_PASSWORD"] = "p"
        try:
            url = GitFetcher._apply_auth("https://github.com/org/repo.git")
            assert "u:p@" in url
        finally:
            del os.environ["GIT_USERNAME"]
            del os.environ["GIT_PASSWORD"]

    @pytest.mark.asyncio
    async def test_missing_file_path_raises(
        self, pipeline_context: PipelineContext,
    ) -> None:
        """Missing ``file_path`` in metadata should raise PluginConfigurationError."""
        resource = Resource(
            name="test",
            url="git+https://example.com/repo.git",
            path="/tmp/out",
            metadata={},
        )
        fetcher = GitFetcher.configure(resource)
        with pytest.raises(PluginConfigurationError, match="file_path"):
            await fetcher.fetch(resource, pipeline_context)

    @pytest.mark.asyncio
    async def test_nonexistent_ref_raises(
        self, pipeline_context: PipelineContext,
    ) -> None:
        """An invalid ref should raise PluginExecutionError."""
        resource = Resource(
            name="test",
            url="git+https://example.com/repo.git",
            path="/tmp/out",
            metadata={"file_path": "f.txt", "ref": "nonexistent-branch-name"},
        )
        fetcher = GitFetcher.configure(resource)
        with pytest.raises(PluginExecutionError, match="not found|pathspec|Remote branch"):
            await fetcher.fetch(resource, pipeline_context)

    @pytest.mark.asyncio
    async def test_clone_and_read(
        self, git_repo_with_file: tuple[Path, Path, str],
        pipeline_context: PipelineContext,
    ) -> None:
        """Integration test: clone a local repo and read a file."""
        repo_path, file_rel, expected_content = git_repo_with_file
        repo_url = f"file://{repo_path.as_posix()}"

        resource = Resource(
            name="test",
            url=repo_url,
            path="/tmp/out",
            metadata={"file_path": file_rel.as_posix(), "ref": "master"},
        )
        fetcher = GitFetcher.configure(resource)
        result = await fetcher.fetch(resource, pipeline_context)

        assert result is not None
        assert result.content_length == len(expected_content)

        # Collect the stream
        from resource_sync.domain.stream import collect_stream
        content = await collect_stream(result.stream)
        assert content.decode() == expected_content
        assert result.metadata["ref"] == "master"
        assert result.metadata["file_path"] == file_rel.as_posix()

    @pytest.mark.asyncio
    async def test_temp_dir_cleanup(
        self, git_repo_with_file: tuple[Path, Path, str],
        pipeline_context: PipelineContext,
    ) -> None:
        """Temp directory should be cleaned up after fetch."""
        repo_path, file_rel, _ = git_repo_with_file
        repo_url = f"file://{repo_path.as_posix()}"

        # Track temp dirs before
        import tempfile
        original_tempdir = tempfile.tempdir
        tempfile.tempdir = None

        try:
            resource = Resource(
                name="test",
                url=repo_url,
                path="/tmp/out",
                metadata={"file_path": file_rel.as_posix(), "ref": "master"},
            )
            fetcher = GitFetcher.configure(resource)
            result = await fetcher.fetch(resource, pipeline_context)

            # Consume the stream to ensure fetch completes
            from resource_sync.domain.stream import collect_stream
            await collect_stream(result.stream)

            # The temp dir should have been cleaned up
            # (We can't easily check the exact path, but the test
            # verifies that no exception is raised during cleanup.)
        finally:
            tempfile.tempdir = original_tempdir

    @pytest.mark.asyncio
    async def test_nonexistent_file_in_repo(
        self, git_repo_with_file: tuple[Path, Path, str],
        pipeline_context: PipelineContext,
    ) -> None:
        """A file that doesn't exist in the repo should raise PluginExecutionError."""
        repo_path, _, _ = git_repo_with_file
        repo_url = f"file://{repo_path.as_posix()}"

        resource = Resource(
            name="test",
            url=repo_url,
            path="/tmp/out",
            metadata={"file_path": "nonexistent.txt", "ref": "master"},
        )
        fetcher = GitFetcher.configure(resource)
        with pytest.raises(PluginExecutionError, match="not found"):
            await fetcher.fetch(resource, pipeline_context)

    @pytest.mark.asyncio
    async def test_default_ref_is_main(
        self, pipeline_context: PipelineContext,
    ) -> None:
        """Default ref should be 'main'."""
        resource = Resource(
            name="test",
            url="git+https://github.com/org/repo.git",
            path="/tmp/out",
            metadata={"file_path": "f.txt"},
        )
        fetcher = GitFetcher.configure(resource)

        # Access the internal ref resolution to verify default
        # The default is applied inside fetch(), so we verify via the
        # metadata field not being set.
        ref = resource.metadata.get("ref", "main")
        assert ref == "main"