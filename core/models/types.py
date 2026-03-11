"""Shared type aliases for reflex records."""

from __future__ import annotations

from typing import Union

from .event import Event
from .metric import CurrentMetric
from .trend import TrendMetric

ReflexRecord = Union[
    CurrentMetric,
    TrendMetric,
    Event,
]
