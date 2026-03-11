"""Collector interface for reflex records."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from ..models.types import ReflexRecord


@dataclass(slots=True)
class BaseCollector(ABC):
    """Base interface for record collectors."""

    name: str
    interval: float

    @abstractmethod
    def start(self) -> None:
        """Start the collector lifecycle."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the collector lifecycle."""

    @abstractmethod
    def collect(self) -> List[ReflexRecord]:
        """Collect a batch of reflex records."""
