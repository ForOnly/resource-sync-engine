"""Tests for PipelineBuilder — plugin assembly and sorting."""

from __future__ import annotations

from pathlib import Path

import pytest

from resource_sync.domain.models import Resource, HashAlgorithm
from resource_sync.engine.builder import PipelineBuilder, _priority_key
from resource_sync.engine.config import Config
from resource_sync.plugin.registry import PluginRegistry


class MockFetcher:
    """A mock fetcher that can be registered for testing."""
    @classmethod
    def configure(cls, resource):
        return cls()

    @classmethod
    def should_apply(cls, resource):
        return True


class MockSink:
    """A mock sink that can be registered for testing."""
    @classmethod
    def configure(cls, resource):
        return cls()


class TestPipelineBuilder:
    """PipelineBuilder — assembles pipelines from plugins."""

    @pytest.fixture
    def registry(self) -> PluginRegistry:
        reg = PluginRegistry()
        reg.register_fetcher(MockFetcher, schemes=frozenset({"https", "http"}))
        reg.register_sink("local", MockSink)
        return reg

    @pytest.fixture
    def builder(self, registry: PluginRegistry) -> PipelineBuilder:
        return PipelineBuilder(registry)

    @pytest.fixture
    def config(self, tmp_path: Path) -> Config:
        return Config(
            resources=[],
            engine_config={},
            repo_root=tmp_path,
        )

    def test_priority_key_default(self) -> None:
        """Classes without priority should default to 500."""
        class NoPriority:
            pass

        assert _priority_key(NoPriority) == 500

    def test_priority_key_custom(self) -> None:
        class WithPriority:
            priority = 100

        assert _priority_key(WithPriority) == 100

    def test_build_with_no_validators(self, builder: PipelineBuilder, config: Config) -> None:
        """A resource should get a pipeline even with no validators."""
        resource = Resource(
            name="test",
            url="https://example.com/f",
            path="/tmp/f",
            algorithm=HashAlgorithm.SHA256,
        )
        pipeline = builder.build(resource, config)
        assert pipeline.source is not None
        assert len(pipeline.validators) == 0
        assert pipeline.sink is not None

    def test_build_dry_run(self, builder: PipelineBuilder, config: Config) -> None:
        """Dry-run pipeline should use drain sink."""
        resource = Resource(
            name="test",
            url="https://example.com/f",
            path="/tmp/f",
            algorithm=HashAlgorithm.SHA256,
        )
        pipeline = builder.build_dry_run(resource, config)
        assert pipeline.source is not None
        assert pipeline.sink is not None
        from resource_sync.sink.drain import DrainSink
        assert isinstance(pipeline.sink, DrainSink)

    def test_unknown_scheme_fails(self, builder: PipelineBuilder, config: Config) -> None:
        """Unregistered URL scheme should raise PluginNotFoundError."""
        resource = Resource(
            name="test",
            url="ftp://example.com/f",
            path="/tmp/f",
            algorithm=HashAlgorithm.SHA256,
        )
        from resource_sync.plugin.registry import PluginNotFoundError
        with pytest.raises(PluginNotFoundError, match="ftp"):
            builder.build(resource, config)

    def test_unknown_sink_fails(self, builder: PipelineBuilder, config: Config) -> None:
        """Unregistered sink name should raise PluginNotFoundError."""
        config = Config(
            resources=[],
            engine_config={"sink": "nonexistent"},
            repo_root=None,
        )
        resource = Resource(
            name="test",
            url="https://example.com/f",
            path="/tmp/f",
            algorithm=HashAlgorithm.SHA256,
        )
        from resource_sync.plugin.registry import PluginNotFoundError
        with pytest.raises(PluginNotFoundError, match="nonexistent"):
            builder.build(resource, config)