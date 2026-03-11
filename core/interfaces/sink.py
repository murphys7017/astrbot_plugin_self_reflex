"""Sink interface for reflex records."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.types import ReflexRecord


class RecordSink(ABC):
    """Base interface for consuming reflex records."""

    @abstractmethod
    async def emit(self, record: ReflexRecord) -> None:
        """Emit a single reflex record to an output target."""
