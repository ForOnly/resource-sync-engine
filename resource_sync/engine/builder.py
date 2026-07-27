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
        sink = self._resolve_sink(resource, config)
        return Pipeline(source=source, validators=tuple(validators), sink=sink)

    def build_dry_run(self, resource: Resource, config: Config) -> Pipeline:
        source = self._resolve_source(resource)
        validators = self._resolve_validators(resource)
        from resource_sync.sink.drain import create_drain_sink
        return Pipeline(source=source, validators=tuple(validators), sink=create_drain_sink())

    def _resolve_source(self, resource: Resource) -> StreamSource:
        scheme = resource.url.split("://", 1)[0].lower()
        fetcher_cls = self._registry.get_fetcher(scheme)
        return fetcher_cls.configure(resource)

    def _resolve_validators(self, resource: Resource) -> list[StreamTransformer]:
        return [v_cls()() for v_cls in self._registry.get_validators() if v_cls.should_apply(resource)]

    def _resolve_sink(self, resource: Resource, config: Config) -> StreamSink | None:
        sink_cls = self._registry.get_sink(config.sink_name)
        return sink_cls.configure(resource)