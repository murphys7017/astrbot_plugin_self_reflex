"""Current metric data model."""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import BaseRecord


@dataclass(slots=True)
class CurrentMetric(BaseRecord):
    """A point-in-time metric value."""

    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)
