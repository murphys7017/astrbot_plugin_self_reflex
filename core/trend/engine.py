"""最小可运行的趋势引擎。"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models.metric import CurrentMetric
from core.models.trend import TrendMetric

from .detector import (
    detect_burst,
    detect_falling_fast,
    detect_rising_fast,
    detect_sustained_high,
)
from .window import MetricWindow


@dataclass(slots=True)
class TrendEngine:
    """将 CurrentMetric 转换为 TrendMetric。"""

    windows: dict[tuple[str, str], MetricWindow] = field(default_factory=dict)

    def process(self, metric: CurrentMetric) -> list[TrendMetric]:
        """处理一个当前指标并返回检测到的趋势。"""
        key = (metric.source, metric.name)
        window = self.windows.setdefault(key, MetricWindow())

        window.add(timestamp=metric.timestamp, value=metric.value)
        values = window.values()
        timestamps = window.timestamps()

        if len(timestamps) >= 2:
            window_span = float(timestamps[-1] - timestamps[0])
        else:
            window_span = 0.0

        trends: list[TrendMetric] = []

        if detect_sustained_high(values, threshold=80):
            trends.append(
                TrendMetric(
                    source=metric.source,
                    timestamp=metric.timestamp,
                    name=metric.name,
                    trend_type="sustained_high",
                    window=window_span,
                    value=metric.value,
                    metadata={"threshold": 80, "samples": window.size()},
                )
            )

        if detect_rising_fast(values, delta=20):
            trends.append(
                TrendMetric(
                    source=metric.source,
                    timestamp=metric.timestamp,
                    name=metric.name,
                    trend_type="rising_fast",
                    window=window_span,
                    value=metric.value,
                    metadata={"delta": 20, "samples": window.size()},
                )
            )

        if detect_falling_fast(values, delta=20):
            trends.append(
                TrendMetric(
                    source=metric.source,
                    timestamp=metric.timestamp,
                    name=metric.name,
                    trend_type="falling_fast",
                    window=window_span,
                    value=metric.value,
                    metadata={"delta": 20, "samples": window.size()},
                )
            )

        if detect_burst(values, delta=30):
            trends.append(
                TrendMetric(
                    source=metric.source,
                    timestamp=metric.timestamp,
                    name=metric.name,
                    trend_type="burst",
                    window=window_span,
                    value=metric.value,
                    metadata={"delta": 30, "samples": window.size()},
                )
            )

        return trends

