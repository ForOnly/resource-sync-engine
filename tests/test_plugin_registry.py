"""Tests for PluginRegistry — registration and query."""

from __future__ import annotations

import pytest

from resource_sync.plugin.errors import PluginError
from resource_sync.plugin.registry import (
    PluginConflictError,
    PluginNotFoundError,
    PluginRegistry,
)


class TestPluginRegistry:
    """PluginRegistry — registration, conflict detection, queries."""

    @pytest.fixture
    def registry(self) -> PluginRegistry:
        return PluginRegistry()

    def test_registry_errors_share_plugin_error_base(self) -> None:
        assert issubclass(PluginConflictError, PluginError)
        assert issubclass(PluginNotFoundError, PluginError)

    def test_register_and_get_fetcher(self, registry: PluginRegistry) -> None:
        class FakeFetcher:
            @classmethod
            def configure(cls, resource):
                return cls()

        registry.register_fetcher(FakeFetcher, schemes=frozenset({"http", "https"}))
        assert registry.get_fetcher("http") is FakeFetcher
        assert registry.get_fetcher("https") is FakeFetcher

    def test_fetcher_conflict(self, registry: PluginRegistry) -> None:
        class FetcherA:
            pass
        class FetcherB:
            pass

        registry.register_fetcher(FetcherA, schemes=frozenset({"http"}))
        with pytest.raises(PluginConflictError, match="http"):
            registry.register_fetcher(FetcherB, schemes=frozenset({"http"}))

    def test_get_missing_fetcher(self, registry: PluginRegistry) -> None:
        with pytest.raises(PluginNotFoundError, match="ftp"):
            registry.get_fetcher("ftp")

    def test_register_and_get_sink(self, registry: PluginRegistry) -> None:
        class FakeSink:
            pass

        registry.register_sink("test_sink", FakeSink)
        assert registry.get_sink("test_sink") is FakeSink

    def test_sink_conflict(self, registry: PluginRegistry) -> None:
        class SinkA:
            pass
        class SinkB:
            pass

        registry.register_sink("test_sink", SinkA)
        with pytest.raises(PluginConflictError, match="test_sink"):
            registry.register_sink("test_sink", SinkB)

    def test_register_and_get_validators(self, registry: PluginRegistry) -> None:
        class ValidatorA:
            pass
        class ValidatorB:
            pass

        registry.register_validator(ValidatorA)
        registry.register_validator(ValidatorB)
        validators = registry.get_validators()
        assert ValidatorA in validators
        assert ValidatorB in validators

    def test_register_and_get_transforms(self, registry: PluginRegistry) -> None:
        class TransformA:
            pass
        class TransformB:
            pass

        registry.register_transform("transform_a", TransformA)
        registry.register_transform("transform_b", TransformB)
        transforms = registry.get_transforms()
        assert TransformA in transforms
        assert TransformB in transforms

    def test_transform_conflict(self, registry: PluginRegistry) -> None:
        class TransformA:
            pass
        class TransformB:
            pass

        registry.register_transform("dup", TransformA)
        with pytest.raises(PluginConflictError, match="dup"):
            registry.register_transform("dup", TransformB)

    def test_get_missing_transform(self, registry: PluginRegistry) -> None:
        with pytest.raises(PluginNotFoundError, match="nonexistent"):
            registry.get_transform("nonexistent")

    def test_register_and_get_observers(self, registry: PluginRegistry) -> None:
        class ObserverA:
            pass

        registry.register_observer(ObserverA)
        observers = registry.get_observers()
        assert ObserverA in observers

    def test_global_registry_singleton(self) -> None:
        from resource_sync.plugin.registry import get_registry
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2