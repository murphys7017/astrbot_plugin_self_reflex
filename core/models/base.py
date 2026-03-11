"""Base data models for reflex records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BaseRecord:
    """Common fields shared by all reflex records."""

    source: str
    timestamp: float
