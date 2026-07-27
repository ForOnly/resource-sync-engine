"""Sync orchestrator — manages the full sync lifecycle."""

from __future__ import annotations

import asyncio
import logging

from resource_sync.domain.events import SyncCompleted, SyncStarted
from resource_sync.domain.models import Resource, ResourceResult, SyncReport, SyncStatus
from resource_sync.domain.stream import CancellationToken
from resource_sync.engine.builder import PipelineBuilder
from resource_sync.engine.config import Config
from resource_sync.engine.executor import PipelineExecutor
from resource_sync.eventbus.memory import EventBus

_LOGGER = logging.getLogger(__name__)


class SyncOrchestrator:
    """Orchestrates the full sync lifecycle with concurrent execution."""

    def __init__(
        self,
        builder: PipelineBuilder,
        executor: PipelineExecutor,
        event_bus: EventBus,
        max_concurrency: int = 1,
    ) -> None:
        self._builder = builder
        self._executor = executor
        self._events = event_bus
        self._max_concurrency = max(1, max_concurrency)

    async def run(
        self,
        config: Config,
        dry_run: bool = False,
        cancel: CancellationToken | None = None,
    ) -> SyncReport:
        """Execute the sync for all resources.

        Uses asyncio.gather() with return_exceptions=True to ensure
        all task results are collected even if some tasks fail or are
        cancelled. This is more robust than TaskGroup for this use case
        because TaskGroup propagates exceptions eagerly.
        """
        cancel = cancel or CancellationToken()
        await self._events.emit(
            SyncStarted(config_summary=f"{len(config.resources)} resources")
        )

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _run_one(
            resource: Resource,
            is_dry_run: bool,
        ) -> ResourceResult:
            """Run a single resource pipeline with concurrency control."""
            async with semaphore:
                if cancel.cancelled:
                    return ResourceResult(
                        resource_name=resource.name,
                        status=SyncStatus.CANCELLED,
                        dry_run=is_dry_run,
                    )
                pipeline = (
                    self._builder.build_dry_run(resource, config)
                    if is_dry_run
                    else self._builder.build(resource, config)
                )
                return await self._executor.execute(
                    pipeline=pipeline,
                    resource=resource,
                    cancel=cancel.child(),
                    config={"dry_run": is_dry_run},
                    env=config.engine_config,
                )

        # Create tasks for all resources
        tasks = [
            _run_one(resource, dry_run) for resource in config.resources
        ]

        # Run all tasks concurrently, collecting all results
        # return_exceptions=True ensures no exception propagates
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results, converting exceptions to error results
        results: list[ResourceResult] = []
        for result in raw_results:
            if isinstance(result, Exception):
                results.append(
                    ResourceResult(
                        resource_name="unknown",
                        status=SyncStatus.ERROR,
                        error_message=f"Task failed: {result}",
                    )
                )
            elif isinstance(result, ResourceResult):
                results.append(result)
                self._log_result(result)
            else:
                results.append(
                    ResourceResult(
                        resource_name="unknown",
                        status=SyncStatus.ERROR,
                        error_message=f"Unexpected result type: {type(result).__name__}",
                    )
                )

        report = SyncReport(dry_run=dry_run, results=tuple(results))
        await self._events.emit(SyncCompleted(summary=str(report.summary)))

        _LOGGER.info(
            "Sync complete — %d created, %d updated, %d skipped, %d errors",
            report.summary.get("created", 0),
            report.summary.get("updated", 0),
            report.summary.get("skipped", 0),
            report.summary.get("error", 0),
        )
        return report

    @staticmethod
    def _log_result(result: ResourceResult) -> None:
        """Log a single sync result at the appropriate level."""
        if result.status == SyncStatus.ERROR:
            _LOGGER.error(
                "  [%s] '%s' — %s",
                result.status.value.upper(),
                result.resource_name,
                result.error_message,
            )
        elif result.status == SyncStatus.CANCELLED:
            _LOGGER.warning(
                "  [%s] '%s'",
                result.status.value.upper(),
                result.resource_name,
            )
        elif result.status == SyncStatus.SKIPPED:
            _LOGGER.info(
                "  [%s] '%s'",
                result.status.value.upper(),
                result.resource_name,
            )
        else:
            _LOGGER.info(
                "  [%s] '%s' (dry_run=%s)",
                result.status.value.upper(),
                result.resource_name,
                result.dry_run,
            )