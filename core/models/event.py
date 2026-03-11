"""Event data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import BaseRecord


@dataclass(slots=True)
class Event(BaseRecord):
    """A structured event emitted by a source."""

    level: str
    type: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
