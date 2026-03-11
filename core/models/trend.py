"""Trend metric data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import BaseRecord


@dataclass(slots=True)
class TrendMetric(BaseRecord):
    """A summarized metric trend over a time window."""

    name: str
    trend_type: str
    window: float
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)
