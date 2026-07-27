"""Plugin system errors."""


class PluginError(Exception):
    """Base exception for plugin errors."""


class PluginConflictError(PluginError):
    """Two plugins conflict (same scheme or name)."""


class PluginNotFoundError(PluginError):
    """A requested plugin was not found."""


class PluginConfigurationError(PluginError):
    """Plugin could not be configured."""


class PluginExecutionError(PluginError):
    """Plugin failed during execution."""