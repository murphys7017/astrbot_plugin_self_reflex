"""NVIDIA GPU 温度专用趋势策略。"""

import json
from datetime import timedelta
from typing import Any, Dict, List, Tuple

from ..models import Observation, Trend, TrendDirection
from .strategy import BaseTrendStrategy


class GpuTemperatureTrendStrategy(BaseTrendStrategy):
    """针对 gpu.temperature_c 的专用趋势分析。"""

    SERIES_IDENTITY_KEYS = ("gpu_index", "name")

    def __init__(
        self,
        window: timedelta,
        interval: timedelta,
        high_temp_threshold_c: float = 85.0,
        recovery_temp_threshold_c: float = 80.0,
        saturation_ratio: float = 0.7,
        min_samples: int = 3,
        name: str = "GpuTemperatureTrendStrategy",
    ) -> None:
        super().__init__(metric="gpu.temperature_c", window=window, interval=interval, name=name)
        self.high_temp_threshold_c = float(high_temp_threshold_c)
        self.recovery_temp_threshold_c = float(recovery_temp_threshold_c)
        self.saturation_ratio = max(0.0, min(1.0, float(saturation_ratio)))
        self.min_samples = max(1, int(min_samples))

    def compute_trends(self, observations: List[Observation]) -> List[Trend]:
        grouped: Dict[str, List[Tuple[Observation, float, Dict[str, Any]]]] = {}
        for obs in observations:
            if not self.covers(obs.metric):
                continue
            try:
                value = float(obs.value)
            except (TypeError, ValueError):
                continue
            series_tags = self._build_series_tags(obs.tags)
            series_key = self._build_series_key(series_tags)
            grouped.setdefault(series_key, []).append((obs, value, series_tags))

        trends: List[Trend] = []
        for series_key, series in grouped.items():
            series.sort(key=lambda item: item[0].timestamp)
            numeric_observations = [item[0] for item in series]
            values = [item[1] for item in series]
            if len(values) < self.min_samples:
                continue

            start_obs = numeric_observations[0]
            end_obs = numeric_observations[-1]
            duration_seconds = (end_obs.timestamp - start_obs.timestamp).total_seconds()
            slope = 0.0 if duration_seconds <= 0 else (values[-1] - values[0]) / duration_seconds
            direction = self._infer_direction(values=values, slope=slope)

            trends.append(
                Trend(
                    metric="gpu.temperature_c",
                    start_time=start_obs.timestamp,
                    end_time=end_obs.timestamp,
                    direction=direction,
                    slope=slope,
                    samples=len(values),
                    series_key=series_key,
                    series_tags=dict(series[-1][2]),
                )
            )
        return trends

    def _infer_direction(self, values: List[float], slope: float) -> TrendDirection:
        high_count = sum(1 for value in values if value >= self.high_temp_threshold_c)
        high_ratio = high_count / len(values)
        if high_ratio >= self.saturation_ratio:
            return TrendDirection.LONG_SATURATION

        if values[-1] <= self.recovery_temp_threshold_c and slope < 0:
            return TrendDirection.DOWN
        if slope > 0:
            return TrendDirection.UP
        return TrendDirection.STABLE

    def _build_series_tags(self, tags: Dict[str, Any]) -> Dict[str, Any]:
        series_tags: Dict[str, Any] = {}
        for key in self.SERIES_IDENTITY_KEYS:
            if key in tags:
                series_tags[key] = tags[key]
        return series_tags

    def _build_series_key(self, series_tags: Dict[str, Any]) -> str:
        if not series_tags:
            return self.metric or "gpu.temperature_c"
        encoded_tags = json.dumps(series_tags, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"{self.metric}:{encoded_tags}"
