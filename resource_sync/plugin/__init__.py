"""Plugin system — registration decorators and registry."""

from resource_sync.plugin.errors import PluginConflictError, PluginNotFoundError
from resource_sync.plugin.registry import (
    PluginRegistry,
    get_registry,
    register_fetcher,
    register_observer,
    register_sink,
    register_transform,
    register_validator,
    register_webhook_platform,
)

__all__ = [
    "PluginConflictError",
    "PluginNotFoundError",
    "PluginRegistry",
    "get_registry",
    "register_fetcher",
    "register_observer",
    "register_sink",
    "register_transform",
    "register_validator",
    "register_webhook_platform",
]