"""Plugin registry — registration and discovery of all plugins.

Uses a decorator-based approach for reliable plugin registration,
avoiding the fragility of @runtime_checkable with ClassVar and
classmethod protocols.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from resource_sync.plugin.errors import PluginConflictError, PluginNotFoundError

_LOGGER = logging.getLogger(__name__)
_PluginT = TypeVar("_PluginT")


class PluginRegistry:
    """Central plugin registry — manages six plugin types.

    Plugin types:
    - ``fetcher`` — data source (HTTP, Git, …)
    - ``validator`` — content safety checks (empty, size, HTML error, …)
    - ``transform`` — stream transformations (identity, decrypt, …)
    - ``sink`` — output destinations (local file, Git, drain, …)
    - ``observer`` — event listeners (log, webhook, …)
    - ``webhook_platform`` — webhook message formatters (DingTalk, Slack, …)
    """

    def __init__(self) -> None:
        self._fetchers: dict[str, Any] = {}
        self._transforms: dict[str, Any] = {}
        self._validators: list[Any] = []
        self._sinks: dict[str, Any] = {}
        self._observers: list[Any] = []
        self._webhook_platforms: dict[str, Any] = {}

    # ─── Registration ───

    def register_fetcher(self, plugin_cls: Any, schemes: frozenset[str]) -> None:
        for scheme in schemes:
            if scheme in self._fetchers:
                raise PluginConflictError(
                    f"Scheme '{scheme}' already registered by {self._fetchers[scheme].__name__}"
                )
            self._fetchers[scheme] = plugin_cls
        _LOGGER.debug("Registered fetcher %s for %s", plugin_cls.__name__, schemes)

    def register_transform(self, name: str, plugin_cls: Any) -> None:
        if name in self._transforms:
            raise PluginConflictError(f"Transform '{name}' already registered")
        self._transforms[name] = plugin_cls
        _LOGGER.debug("Registered transform '%s': %s", name, plugin_cls.__name__)

    def register_validator(self, plugin_cls: Any) -> None:
        self._validators.append(plugin_cls)
        _LOGGER.debug("Registered validator: %s", plugin_cls.__name__)

    def register_sink(self, name: str, plugin_cls: Any) -> None:
        if name in self._sinks:
            raise PluginConflictError(f"Sink '{name}' already registered")
        self._sinks[name] = plugin_cls
        _LOGGER.debug("Registered sink '%s': %s", name, plugin_cls.__name__)

    def register_observer(self, plugin_cls: Any) -> None:
        self._observers.append(plugin_cls)
        _LOGGER.debug("Registered observer: %s", plugin_cls.__name__)

    # ─── Webhook platform registration ───

    def register_webhook_platform(self, name: str, plugin_cls: Any) -> None:
        if name in self._webhook_platforms:
            raise PluginConflictError(
                f"Webhook platform '{name}' already registered by "
                f"{self._webhook_platforms[name].__name__}"
            )
        self._webhook_platforms[name] = plugin_cls
        _LOGGER.debug("Registered webhook platform '%s': %s", name, plugin_cls.__name__)

    def get_webhook_platform(self, name: str) -> Any:
        if name not in self._webhook_platforms:
            raise PluginNotFoundError(f"No webhook platform: '{name}'")
        return self._webhook_platforms[name]

    # ─── Query ───

    def get_fetcher(self, scheme: str) -> Any:
        if scheme not in self._fetchers:
            raise PluginNotFoundError(f"No fetcher for scheme: '{scheme}'")
        return self._fetchers[scheme]

    def get_transform(self, name: str) -> Any:
        if name not in self._transforms:
            raise PluginNotFoundError(f"No transform: '{name}'")
        return self._transforms[name]

    def get_transforms(self) -> list[Any]:
        """Return all registered transforms as a list (for iteration)."""
        return list(self._transforms.values())

    def get_validators(self) -> list[Any]:
        return list(self._validators)

    def get_sink(self, name: str) -> Any:
        if name not in self._sinks:
            raise PluginNotFoundError(f"No sink: '{name}'")
        return self._sinks[name]

    def get_observers(self) -> list[Any]:
        return list(self._observers)

    def get_observer(self, name: str) -> Any:
        """Look up an observer plugin class by name.

        Raises ``PluginNotFoundError`` if no observer with the given
        name is registered.
        """
        for cls in self._observers:
            if getattr(cls, "name", "") == name:
                return cls
        raise PluginNotFoundError(f"No observer: '{name}'")


# ─── Global registry instance ───

_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get or create the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


# ─── Decorators ───

def register_fetcher(schemes: frozenset[str]) -> Callable[[_PluginT], _PluginT]:
    """Decorator: register a fetcher plugin class."""
    def decorator(cls: _PluginT) -> _PluginT:
        get_registry().register_fetcher(cls, schemes)
        return cls
    return decorator


def register_transform(name: str) -> Callable[[_PluginT], _PluginT]:
    """Decorator: register a transform plugin class."""
    def decorator(cls: _PluginT) -> _PluginT:
        get_registry().register_transform(name, cls)
        return cls
    return decorator


def register_validator(cls: _PluginT) -> _PluginT:
    """Decorator: register a validator plugin class."""
    get_registry().register_validator(cls)
    return cls


def register_sink(name: str) -> Callable[[_PluginT], _PluginT]:
    """Decorator: register a sink plugin class."""
    def decorator(cls: _PluginT) -> _PluginT:
        get_registry().register_sink(name, cls)
        return cls
    return decorator


def register_observer(cls: _PluginT) -> _PluginT:
    """Decorator: register an observer plugin class."""
    get_registry().register_observer(cls)
    return cls


def register_webhook_platform(name: str) -> Callable[[_PluginT], _PluginT]:
    """Decorator: register a webhook platform plugin class.

    The decorated class must implement the ``WebhookPlatform`` protocol
    (or subclass ``WebhookPlatformBase``) and set ``name: ClassVar[str]``
    to match the registered name.

    Usage::

        @register_webhook_platform("my_platform")
        class MyPlatform(WebhookPlatformBase):
            name = "my_platform"

            def _make_message(self, text: str, title: str) -> dict:
                return {"my": "format", "text": text}

    The platform can then be used in ``config.yaml``:

    .. code-block:: yaml

       engine:
         observers:
           - type: webhook
             platform: my_platform
             url: "${WEBHOOK_URL}"
    """
    def decorator(cls: _PluginT) -> _PluginT:
        get_registry().register_webhook_platform(name, cls)
        return cls
    return decorator