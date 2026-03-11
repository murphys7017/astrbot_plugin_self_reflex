"""当前指标数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import BaseRecord


@dataclass(slots=True)
class CurrentMetric(BaseRecord):
    """某一时刻采集到的即时指标值。"""

    # 指标名，例如 cpu_usage、memory_used
    name: str
    # 指标值
    value: float
    # 维度标签，例如 {"host": "node-1"}
    tags: dict[str, str] = field(default_factory=dict)
