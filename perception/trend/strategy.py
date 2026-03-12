"""趋势分析策略定义。"""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import List, Optional

from ..models import Observation, Trend


class BaseTrendStrategy(ABC):
    """
    趋势策略抽象基类。

    所有策略必须声明：
    - window: 策略分析所需的时间窗口
    - interval: 策略执行间隔
    - covers(metric): 当前策略是否接管某个 metric
    """

    metric: Optional[str]
    window: timedelta
    interval: timedelta
    name: str
    _last_run: Optional[float]

    def __init__(
        self,
        metric: Optional[str],
        window: timedelta,
        interval: Optional[timedelta] = None,
        name: Optional[str] = None,
    ) -> None:
        # interval 默认复用 window，保证“窗口采样”与“调度频率”一致。
        self.metric = metric
        self.window = window
        self.interval = interval if interval is not None else window
        self.name = name or self.__class__.__name__
        self._last_run = None

    @abstractmethod
    def compute_trends(self, observations: List[Observation]) -> List[Trend]:
        """
        根据 Observation 列表计算趋势结果。

        Args:
            observations: 输入观测数据。

        Returns:
            Trend 列表；若输入为空或无法计算可返回空列表。
        """
        raise NotImplementedError

    def covers(self, metric: str) -> bool:
        """判断当前策略是否接管某个 metric。"""
        return self.metric is None or self.metric == metric

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
