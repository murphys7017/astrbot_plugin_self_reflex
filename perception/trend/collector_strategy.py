"""具体趋势策略实现。"""

from datetime import timedelta
from typing import List, Optional

from astrbot.api import logger
from perception.models import Observation, Trend, TrendDirection
from perception.trend.strategy import BaseTrendStrategy


class CollectorTrendStrategy(BaseTrendStrategy):
    """
    通用指标趋势策略示例。

    说明：
    - 仅处理可转为 float 的 observation.value
    - 基于首尾值与时间差计算 slope
    - 根据斜率和阈值推断 TrendDirection
    """

    def __init__(
        self,
        metric: str,
        window: timedelta,
        stable_epsilon: float = 1e-6,
        rapid_delta_threshold: float = 0.2,
        saturation_threshold: float = 0.9,
        saturation_ratio: float = 0.8,
        interval: Optional[timedelta] = None,
    ) -> None:
        super().__init__(metric=metric, window=window, interval=interval)
        self.stable_epsilon = stable_epsilon
        self.rapid_delta_threshold = rapid_delta_threshold
        self.saturation_threshold = saturation_threshold
        self.saturation_ratio = saturation_ratio

    def compute_trend(self, observations: List[Observation]) -> Optional[Trend]:
        if not observations:
            logger.debug("CollectorTrendStrategy: empty observations, skip")
            return None

        metric_observations = [obs for obs in observations if obs.metric == self.metric]
        if not metric_observations:
            logger.debug(f"CollectorTrendStrategy: no matched metric={self.metric}")
            return None

        metric_observations.sort(key=lambda o: o.timestamp)

        numeric_values: List[float] = []
        numeric_observations: List[Observation] = []
        for obs in metric_observations:
            try:
                numeric_values.append(float(obs.value))
                numeric_observations.append(obs)
            except (TypeError, ValueError):
                continue

        if not numeric_observations:
            logger.debug(f"CollectorTrendStrategy: no numeric observations for metric={self.metric}")
            return None

        start_obs = numeric_observations[0]
        end_obs = numeric_observations[-1]
        start_value = numeric_values[0]
        end_value = numeric_values[-1]

        duration_seconds = (end_obs.timestamp - start_obs.timestamp).total_seconds()
        if duration_seconds <= 0:
            slope = 0.0
        else:
            slope = (end_value - start_value) / duration_seconds

        delta = end_value - start_value
        direction = self._infer_direction(
            values=numeric_values,
            delta=delta,
            slope=slope,
        )

        return Trend(
            metric=self.metric,
            start_time=start_obs.timestamp,
            end_time=end_obs.timestamp,
            direction=direction,
            slope=slope,
            samples=len(numeric_observations),
        )

    def _infer_direction(self, values: List[float], delta: float, slope: float) -> TrendDirection:
        """根据值序列和变化速率判断趋势方向。"""
        if not values:
            return TrendDirection.STABLE

        if self._is_long_saturation(values):
            return TrendDirection.LONG_SATURATION

        if abs(delta) <= self.stable_epsilon and abs(slope) <= self.stable_epsilon:
            return TrendDirection.STABLE

        if abs(delta) >= self.rapid_delta_threshold:
            return TrendDirection.RAPID_RISE if delta > 0 else TrendDirection.RAPID_DROP

        return TrendDirection.UP if slope > 0 else TrendDirection.DOWN

    def _is_long_saturation(self, values: List[float]) -> bool:
        """判断是否出现长时间高位占满。"""
        if len(values) < 3:
            return False

        high_count = sum(1 for value in values if value >= self.saturation_threshold)
        return (high_count / len(values)) >= self.saturation_ratio
