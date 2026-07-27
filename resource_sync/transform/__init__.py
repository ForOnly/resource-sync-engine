"""Transform plugins — stream transformation implementations.

Transforms sit between validators and the sink in the pipeline:
  source → validators → transforms → sink

Each transform receives a stream, transforms it, and returns a new stream.
Add new transform modules here and import them so the registration
decorators fire.
"""
from resource_sync.transform import identity  # noqa: F401