"""Pipeline builder — assembles pipelines from config and plugins."""

from __future__ import annotations

from resource_sync.domain.models import Resource
from resource_sync.domain.pipeline import Pipeline
from resource_sync.domain.stream import StreamSink, StreamSource, StreamTransformer
from resource_sync.engine.config import Config
from resource_sync.plugin.registry import PluginRegistry


class PipelineBuilder:
    """Assembles a Pipeline for each resource based on config and registry."""

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def build(self, resource: Resource, config: Config) -> Pipeline:
        source = self._resolve_source(resource)
        validators = self._resolve_validators(resource)
        transforms = self._resolve_transforms(resource)
        sink = self._resolve_sink(resource, config)
        return Pipeline(
            source=source,
            validators=tuple(validators),
            transforms=tuple(transforms),
            sink=sink,
        )

    def build_dry_run(self, resource: Resource, config: Config) -> Pipeline:
        source = self._resolve_source(resource)
        validators = self._resolve_validators(resource)
        transforms = self._resolve_transforms(resource)
        from resource_sync.sink.drain import create_drain_sink
        return Pipeline(
            source=source,
            validators=tuple(validators),
            transforms=tuple(transforms),
            sink=create_drain_sink(),
        )

    def _resolve_source(self, resource: Resource) -> StreamSource:
        scheme = resource.url.split("://", 1)[0].lower()
        fetcher_cls = self._registry.get_fetcher(scheme)
        return fetcher_cls.configure(resource)

    def _resolve_validators(self, resource: Resource) -> list[StreamTransformer]:
        validators = [
            v_cls()()
            for v_cls in self._registry.get_validators()
            if v_cls.should_apply(resource)
        ]
        # Sort by priority (lower number = earlier), stable sort preserves
        # registration order for equal priorities
        validators.sort(key=_priority_key)
        return validators

    def _resolve_transforms(self, resource: Resource) -> list[StreamTransformer]:
        transforms = [
            t_cls()()
            for t_cls in self._registry.get_transforms()
            if t_cls.should_apply(resource)
        ]
        # Sort by priority (lower number = earlier)
        transforms.sort(key=_priority_key)
        return transforms

    def _resolve_sink(self, resource: Resource, config: Config) -> StreamSink | None:
        sink_cls = self._registry.get_sink(config.sink_name)
        return sink_cls.configure(resource)


def _priority_key(cls_or_callable) -> int:
    """Extract priority from a plugin instance or class.

    Plugins that don't define a priority default to 500 (middle).
    """
    return getattr(cls_or_callable, "priority", 500)