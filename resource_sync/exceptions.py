"""
Custom exception hierarchy for the Resource Sync Engine.

Every domain exception inherits from ``ResourceSyncError`` so callers can
catch the base type for logging / reporting while still having specific
types for targeted handling.
"""


class ResourceSyncError(Exception):
    """Base exception for all domain errors."""


class ConfigError(ResourceSyncError):
    """Configuration file is missing, invalid, or violates the schema."""


class DownloadError(ResourceSyncError):
    """Network failure, non-2xx HTTP status, or timeout during download."""


class HashError(ResourceSyncError):
    """File read failure during hash computation."""


class ContentError(ResourceSyncError):
    """Downloaded content failed validation (empty, too large, or an HTML error page)."""


class GitError(ResourceSyncError):
    """Git command failure (staging, commit, or push)."""