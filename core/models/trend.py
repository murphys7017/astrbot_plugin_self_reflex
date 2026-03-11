"""趋势指标数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import BaseRecord


@dataclass(slots=True)
class TrendMetric(BaseRecord):
    """在时间窗口内聚合得到的趋势指标。"""

    # 指标名
    name: str
    # 趋势类型，例如 avg、p95、slope
    trend_type: str
    # 统计窗口大小（秒）
    window: float
    # 趋势计算结果值
    value: float
    # 附加元数据，例如采样点数、算法参数
    metadata: dict[str, Any] = field(default_factory=dict)
