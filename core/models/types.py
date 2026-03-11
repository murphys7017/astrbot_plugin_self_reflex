"""Reflex 记录的共享类型定义。"""

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
"""统一的记录类型别名，用于接口层声明输入/输出。"""
