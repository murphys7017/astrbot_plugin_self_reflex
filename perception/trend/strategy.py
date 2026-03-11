"""趋势分析策略定义。"""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import List, Optional

from perception.models import Observation, Trend


class BaseTrendStrategy(ABC):
    """
    趋势策略抽象基类。

    所有策略必须声明：
    - metric: 策略处理的指标名称
    - window: 策略分析所需的时间窗口
    - interval: 策略执行间隔
    """

    metric: str
    window: timedelta
    interval: timedelta
    _last_run: Optional[float]

    def __init__(self, metric: str, window: timedelta, interval: Optional[timedelta] = None) -> None:
        # interval 默认复用 window，保证“窗口采样”与“调度频率”一致。
        self.metric = metric
        self.window = window
        self.interval = interval if interval is not None else window
        self._last_run = None

    @abstractmethod
    def compute_trend(self, observations: List[Observation]) -> Optional[Trend]:
        """
        根据 Observation 列表计算趋势。

        Args:
            observations: 输入观测数据。

        Returns:
            Trend 对象；若输入为空或无法计算可返回 None。
        """
        raise NotImplementedError

    def should_run(self, now: float) -> bool:
        """
        根据 interval 判断策略当前是否应执行。

        Args:
            now: 当前时间戳（秒）。
        """
        if self._last_run is None:
            return True

        interval_seconds = self.interval.total_seconds()
        if interval_seconds <= 0:
            return True

        return (now - self._last_run) >= interval_seconds
