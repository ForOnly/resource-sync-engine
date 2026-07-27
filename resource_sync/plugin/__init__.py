"""Plugin system — registration decorators and registry."""
from resource_sync.plugin.registry import (
    PluginConflictError,
    PluginNotFoundError,
    PluginRegistry,
    get_registry,
    register_fetcher,
    register_observer,
    register_sink,
    register_transform,
    register_validator,
)