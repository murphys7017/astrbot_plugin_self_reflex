"""通用趋势策略实现。"""

import json
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger
from ..models import Observation, Trend, TrendDirection
from .strategy import BaseTrendStrategy


class FallbackMetricTrendStrategy(BaseTrendStrategy):
    """
    兜底数值型趋势策略。

    说明：
    - 支持单 metric 或全量 metric 模式
    - 按 metric + series_key 进行序列分组
    - 仅处理可转为 float 的 observation.value
    - 基于首尾值与时间差计算 slope
    - 根据斜率和阈值推断 TrendDirection
    """

    SERIES_IDENTITY_KEYS = ("pid", "name", "rank", "status")

    def __init__(
        self,
        window: timedelta,
        metric: Optional[str] = None,
        min_samples: int = 3,
        stable_epsilon: float = 1e-6,
        rapid_delta_threshold: float = 0.2,
        saturation_threshold: float = 0.9,
        saturation_ratio: float = 0.8,
        interval: Optional[timedelta] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(metric=metric, window=window, interval=interval, name=name)
        self.min_samples = max(1, int(min_samples))
        self.stable_epsilon = stable_epsilon
        self.rapid_delta_threshold = rapid_delta_threshold
        self.saturation_threshold = saturation_threshold
        self.saturation_ratio = saturation_ratio

    def compute_trends(self, observations: List[Observation]) -> List[Trend]:
        if not observations:
            logger.debug(f"{self.name}: empty observations, skip")
            return []

        grouped = self._group_numeric_observations(observations)
        trends: List[Trend] = []
        for (metric, series_key), series in grouped.items():
            series.sort(key=lambda item: item[0].timestamp)
            numeric_observations = [item[0] for item in series]
            numeric_values = [item[1] for item in series]
            series_tags = dict(series[0][2])

            if len(numeric_observations) < self.min_samples:
                logger.debug(
                    f"{self.name}: insufficient samples for metric={metric} "
                    f"series_key={series_key} samples={len(numeric_observations)}"
                )
                continue

            start_obs = numeric_observations[0]
            end_obs = numeric_observations[-1]
            start_value = numeric_values[0]
            end_value = numeric_values[-1]
            duration_seconds = (end_obs.timestamp - start_obs.timestamp).total_seconds()
            slope = 0.0 if duration_seconds <= 0 else (end_value - start_value) / duration_seconds
            delta = end_value - start_value
            direction = self._infer_direction(values=numeric_values, delta=delta, slope=slope)
            trends.append(
                Trend(
                    metric=metric,
                    start_time=start_obs.timestamp,
                    end_time=end_obs.timestamp,
                    direction=direction,
                    slope=slope,
                    samples=len(numeric_observations),
                    series_key=series_key,
                    series_tags=series_tags,
                )
            )

        return trends

    def _group_numeric_observations(
        self,
        observations: List[Observation],
    ) -> Dict[Tuple[str, str], List[Tuple[Observation, float, Dict[str, Any]]]]:
        """按 metric + series_key 聚合数值型 Observation。"""
        grouped: Dict[Tuple[str, str], List[Tuple[Observation, float, Dict[str, Any]]]] = {}
        for obs in observations:
            if not self.covers(obs.metric):
                continue
            try:
                numeric_value = float(obs.value)
            except (TypeError, ValueError):
                continue

            series_tags = self._build_series_tags(obs.tags)
            series_key = self._build_series_key(obs.metric, series_tags)
            grouped.setdefault((obs.metric, series_key), []).append((obs, numeric_value, series_tags))
        return grouped

    def _build_series_tags(self, tags: Dict[str, Any]) -> Dict[str, Any]:
        """提取可用于趋势分组的稳定标签。"""
        series_tags: Dict[str, Any] = {}
        for key in self.SERIES_IDENTITY_KEYS:
            if key in tags:
                series_tags[key] = tags[key]

        if series_tags:
            return series_tags

        for key in sorted(tags):
            value = tags[key]
            if isinstance(value, (str, int, float, bool)) or value is None:
                series_tags[key] = value
        return series_tags

    def _build_series_key(self, metric: str, series_tags: Dict[str, Any]) -> str:
        """生成趋势序列唯一键。"""
        if not series_tags:
            return metric
        encoded_tags = json.dumps(series_tags, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"{metric}:{encoded_tags}"

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


CollectorTrendStrategy = FallbackMetricTrendStrategy
