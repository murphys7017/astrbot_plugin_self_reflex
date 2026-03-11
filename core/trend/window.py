"""滑动窗口数据结构。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class Sample:
    """单个采样点。"""

    timestamp: float
    value: float


@dataclass(slots=True)
class MetricWindow:
    """固定长度的指标窗口（最多 10 个样本）。"""

    samples: deque[Sample] = field(default_factory=lambda: deque(maxlen=10))

    def add(self, timestamp: float, value: float) -> None:
        """新增一个采样点。"""
        self.samples.append(Sample(timestamp=timestamp, value=value))

    def values(self) -> list[float]:
        """返回窗口内所有值。"""
        return [sample.value for sample in self.samples]

    def timestamps(self) -> list[float]:
        """返回窗口内所有时间戳。"""
        return [sample.timestamp for sample in self.samples]

    def size(self) -> int:
        """返回窗口当前样本数量。"""
        return len(self.samples)

