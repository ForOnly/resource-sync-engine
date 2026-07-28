"""Tests for SyncOrchestrator — the full sync lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from resource_sync.domain.events import Event, SyncCompleted, SyncStarted
from resource_sync.domain.models import SyncReport
from resource_sync.engine.builder import PipelineBuilder
from resource_sync.engine.config import Config
from resource_sync.engine.executor import PipelineExecutor
from resource_sync.engine.orchestrator import SyncOrchestrator
from resource_sync.eventbus.memory import EventBus
from resource_sync.plugin.registry import PluginRegistry


class TestSyncOrchestrator:
    """SyncOrchestrator — full sync lifecycle."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        return EventBus()

    @pytest.fixture
    def orchestrator(self, event_bus: EventBus) -> SyncOrchestrator:
        return SyncOrchestrator(
            builder=PipelineBuilder(PluginRegistry()),
            executor=PipelineExecutor(event_bus),
            event_bus=event_bus,
        )

    @pytest.mark.asyncio
    async def test_run_emits_only_sync_started(
        self,
        event_bus: EventBus,
        orchestrator: SyncOrchestrator,
        tmp_path: Path,
    ) -> None:
        """Orchestrator starts resource processing; CLI owns final completion."""
        events: list[str] = []

        async def track(event: Event) -> None:
            events.append(type(event).__name__)

        event_bus.subscribe_handler(SyncStarted, track)
        event_bus.subscribe_handler(SyncCompleted, track)

        report = await orchestrator.run(
            Config(resources=(), engine_config={}, repo_root=tmp_path),
            dry_run=True,
        )

        assert isinstance(report, SyncReport)
        assert events == ["SyncStarted"]

    @pytest.mark.asyncio
    async def test_empty_report_on_empty_config(
        self,
        orchestrator: SyncOrchestrator,
        tmp_path: Path,
    ) -> None:
        """Orchestrator should handle empty config gracefully."""
        config = Config(resources=(), engine_config={}, repo_root=tmp_path)
        report = await orchestrator.run(config, dry_run=True)

        assert isinstance(report, SyncReport)
        assert len(report.results) == 0

    def test_commit_changes_no_changes(self, orchestrator: SyncOrchestrator) -> None:
        """commit_changes with no changes should return True."""
        result = orchestrator.commit_changes(repo_root=None, changed=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_shutdown(self, orchestrator: SyncOrchestrator) -> None:
        """shutdown should not raise."""
        await orchestrator.shutdown()