"""Pipeline declaration — describes how a single resource is processed."""

from __future__ import annotations

from dataclasses import dataclass

from resource_sync.domain.stream import StreamSink, StreamSource, StreamTransformer


@dataclass(frozen=True)
class Pipeline:
    """Declarative pipeline for processing a single resource.

    Stages are executed in order:
    1. source      — fetch the data stream
    2. validators  — validate content (size, emptiness, HTML errors)
    3. transforms  — transform content (decompress, decrypt, render)
    4. sink        — persist the data (hash comparison is done in the executor)
    """

    source: StreamSource
    validators: tuple[StreamTransformer, ...] = ()
    transforms: tuple[StreamTransformer, ...] = ()
    sink: StreamSink | None = None

    @property
    def stage_count(self) -> int:
        """Total number of stages in this pipeline."""
        count = 1  # source
        count += len(self.validators)
        count += len(self.transforms)
        if self.sink is not None:
            count += 1
        return count