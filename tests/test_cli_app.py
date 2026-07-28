"""Tests for CLI finalization and completion notification ordering."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from resource_sync.cli import app
from resource_sync.domain.events import Event, SyncCompleted
from resource_sync.domain.models import ResourceResult, SyncReport, SyncStatus
from resource_sync.engine.config import Config
from resource_sync.engine.orchestrator import SyncOrchestrator
from resource_sync.eventbus.memory import EventBus


class _FakeOrchestrator:
    def __init__(
        self,
        report: SyncReport,
        timeline: list[str],
        git_succeeded: bool = True,
    ) -> None:
        self._report = report
        self._timeline = timeline
        self._git_succeeded = git_succeeded

    async def run(self, config: Config, dry_run: bool = False) -> SyncReport:
        self._timeline.append("run")
        return self._report

    def commit_changes(self, repo_root: str | None, changed: int) -> bool:
        self._timeline.append("git")
        return self._git_succeeded

    async def shutdown(self) -> None:
        self._timeline.append("shutdown")


def _changed_report() -> SyncReport:
    return SyncReport(
        results=(
            ResourceResult(
                resource_name="rules",
                status=SyncStatus.UPDATED,
            ),
        ),
    )


def _error_report() -> SyncReport:
    return SyncReport(
        results=(
            ResourceResult(
                resource_name="rules",
                status=SyncStatus.ERROR,
                error_message="download failed",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_completion_is_emitted_after_report_and_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[str] = []
    event_bus = EventBus()

    async def record_completion(event: Event) -> None:
        timeline.append(type(event).__name__)

    event_bus.subscribe_handler(SyncCompleted, record_completion)
    monkeypatch.setattr(
        app,
        "_write_report",
        lambda report_json, repo_root: timeline.append("report") or True,
    )
    orchestrator = cast(
        SyncOrchestrator,
        _FakeOrchestrator(_changed_report(), timeline),
    )

    report, report_written, git_succeeded = await app._run_and_finalize(
        orchestrator=orchestrator,
        event_bus=event_bus,
        config=Config(resources=(), repo_root=tmp_path),
        config_path=tmp_path / "config.yaml",
        repo_root=tmp_path,
        dry_run=False,
        no_commit=False,
    )

    assert report.changed == 1
    assert report_written is True
    assert git_succeeded is True
    assert timeline == ["run", "report", "git", "SyncCompleted", "shutdown"]


@pytest.mark.asyncio
async def test_completion_is_not_emitted_when_git_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[str] = []
    event_bus = EventBus()

    async def record_completion(event: Event) -> None:
        timeline.append(type(event).__name__)

    event_bus.subscribe_handler(SyncCompleted, record_completion)
    monkeypatch.setattr(app, "_write_report", lambda report_json, repo_root: True)
    orchestrator = cast(
        SyncOrchestrator,
        _FakeOrchestrator(_changed_report(), timeline, git_succeeded=False),
    )

    _, report_written, git_succeeded = await app._run_and_finalize(
        orchestrator=orchestrator,
        event_bus=event_bus,
        config=Config(resources=(), repo_root=tmp_path),
        config_path=tmp_path / "config.yaml",
        repo_root=tmp_path,
        dry_run=False,
        no_commit=False,
    )

    assert report_written is True
    assert git_succeeded is False
    assert "SyncCompleted" not in timeline
    assert timeline == ["run", "git", "shutdown"]


@pytest.mark.asyncio
async def test_completion_is_not_emitted_when_report_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[str] = []
    event_bus = EventBus()

    async def record_completion(event: Event) -> None:
        timeline.append(type(event).__name__)

    event_bus.subscribe_handler(SyncCompleted, record_completion)
    monkeypatch.setattr(app, "_write_report", lambda report_json, repo_root: False)
    orchestrator = cast(
        SyncOrchestrator,
        _FakeOrchestrator(SyncReport(), timeline),
    )

    _, report_written, git_succeeded = await app._run_and_finalize(
        orchestrator=orchestrator,
        event_bus=event_bus,
        config=Config(resources=(), repo_root=tmp_path),
        config_path=tmp_path / "config.yaml",
        repo_root=tmp_path,
        dry_run=False,
        no_commit=False,
    )

    assert report_written is False
    assert git_succeeded is True
    assert timeline == ["run", "shutdown"]


@pytest.mark.asyncio
async def test_completion_is_not_emitted_when_resources_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[str] = []
    event_bus = EventBus()

    async def record_completion(event: Event) -> None:
        timeline.append(type(event).__name__)

    event_bus.subscribe_handler(SyncCompleted, record_completion)
    monkeypatch.setattr(app, "_write_report", lambda report_json, repo_root: True)
    orchestrator = cast(
        SyncOrchestrator,
        _FakeOrchestrator(_error_report(), timeline),
    )

    report, report_written, git_succeeded = await app._run_and_finalize(
        orchestrator=orchestrator,
        event_bus=event_bus,
        config=Config(resources=(), repo_root=tmp_path),
        config_path=tmp_path / "config.yaml",
        repo_root=tmp_path,
        dry_run=False,
        no_commit=False,
    )

    assert report.has_errors is True
    assert report_written is True
    assert git_succeeded is True
    assert timeline == ["run", "shutdown"]


@pytest.mark.asyncio
async def test_dry_run_skips_git_and_emits_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[str] = []
    event_bus = EventBus()

    async def record_completion(event: Event) -> None:
        timeline.append(type(event).__name__)

    event_bus.subscribe_handler(SyncCompleted, record_completion)
    monkeypatch.setattr(
        app,
        "_write_report",
        lambda report_json, repo_root: timeline.append("report") or True,
    )
    orchestrator = cast(
        SyncOrchestrator,
        _FakeOrchestrator(_changed_report(), timeline),
    )

    _, _, git_succeeded = await app._run_and_finalize(
        orchestrator=orchestrator,
        event_bus=event_bus,
        config=Config(resources=(), repo_root=tmp_path),
        config_path=tmp_path / "config.yaml",
        repo_root=tmp_path,
        dry_run=True,
        no_commit=False,
    )

    assert git_succeeded is True
    assert timeline == ["run", "report", "SyncCompleted", "shutdown"]
