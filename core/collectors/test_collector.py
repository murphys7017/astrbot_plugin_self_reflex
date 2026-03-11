"""最小测试采集器实现。"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from core.interfaces.collector import BaseCollector
from core.models.metric import CurrentMetric
from core.models.types import ReflexRecord


@dataclass(slots=True)
class RandomCPUCollector(BaseCollector):
    """每次生成随机 cpu_usage 的测试采集器。"""

    name: str = "hardware"
    interval: float = 5.0
    _running: bool = field(default=False, init=False, repr=False)
    _last_value: float = field(default=50.0, init=False, repr=False)

    def start(self) -> None:
        """启动采集。"""
        self._running = True

    def stop(self) -> None:
        """停止采集。"""
        self._running = False

    def collect(self) -> list[ReflexRecord]:
        """采集一次随机 CPU 指标。"""
        if not self._running:
            self.start()

        drift = random.uniform(-8.0, 8.0)
        if random.random() < 0.15:
            drift += random.choice((-30.0, 30.0))

        self._last_value = max(0.0, min(100.0, self._last_value + drift))

        metric = CurrentMetric(
            source=self.name,
            timestamp=time.time(),
            name="cpu_usage",
            value=round(self._last_value, 2),
            tags={"core": "all"},
        )
        return [metric]
