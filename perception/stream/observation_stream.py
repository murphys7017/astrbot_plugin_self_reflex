"""ObservationStream：感知层 Observation 数据总线。"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

from astrbot.api import logger
from ..models import Observation


class ObservationStream:
    """
    Observation 流缓存与查询组件。

    职责：
    1. 按时间窗口维护 Observation 缓冲区
    2. 维护 source/metric 到 buffer 下标的索引
    3. 提供按时间段与 source/metric 的查询能力
    """

    buffer: List[Observation]
    index: Dict[str, Dict[str, List[int]]]
    time_window: timedelta

    def __init__(self, time_window: timedelta) -> None:
        """
        初始化 ObservationStream。

        Args:
            time_window: Observation 保留时间窗口。
        """
        self.buffer = []
        self.index = defaultdict(lambda: defaultdict(list))
        self.time_window = time_window
        logger.info(f"ObservationStream initialized: time_window={self.time_window.total_seconds()}s")

    def push(self, obs: Observation) -> None:
        """
        写入单条 Observation，更新 buffer 和 index，并清理过期数据。

        Args:
            obs: 单条观测数据。
        """
        if self._should_drop(obs):
            return

        self._append(obs)
        self._cleanup()

    def push_many(self, observations: Iterable[Observation]) -> None:
        """
        批量写入 Observation。

        Args:
            observations: 可迭代观测数据。
        """
        has_new_data = False
        for obs in observations:
            if self._should_drop(obs):
                continue
            self._append(obs)
            has_new_data = True

        if has_new_data:
            self._cleanup()

    def get_window(
        self,
        start: datetime,
        end: datetime,
        source: Optional[str] = None,
        metric: Optional[str] = None,
    ) -> List[Observation]:
        """
        获取指定时间段内的 Observation。

        当 source/metric 提供时，优先使用 index 获取候选下标，再按时间过滤。

        Args:
            start: 查询起始时间（含边界）。
            end: 查询结束时间（含边界）。
            source: 可选来源过滤（例如 "cpu"）。
            metric: 可选指标过滤。

        Returns:
            匹配条件的 Observation 列表。
        """
        if start > end:
            return []

        self._cleanup()
        if not self.buffer:
            return []

        indices: Optional[List[int]] = self._candidate_indices(
            source=self._normalize_source(source),
            metric=metric,
        )
        if indices is None:
            candidates = self.buffer
        else:
            candidates = [self.buffer[i] for i in indices if 0 <= i < len(self.buffer)]

        results: List[Observation] = []
        for obs in candidates:
            if start <= obs.timestamp <= end:
                results.append(obs)
        return results

    def _cleanup(self) -> None:
        """
        清理超过时间窗口的数据，并同步更新索引。

        以当前系统时间为基准，保留 timestamp >= now - time_window 的数据。
        """
        if not self.buffer:
            return

        cutoff = datetime.now() - self.time_window
        original_size = len(self.buffer)
        self.buffer = [obs for obs in self.buffer if obs.timestamp >= cutoff]

        if len(self.buffer) != original_size:
            self._rebuild_index()

    def _append(self, obs: Observation) -> None:
        """向 buffer 追加数据并增量更新 index。"""
        self.buffer.append(obs)
        idx = len(self.buffer) - 1
        source_key = obs.source.value
        self.index[source_key][obs.metric].append(idx)

    def _rebuild_index(self) -> None:
        """基于当前 buffer 重新构建 source/metric 索引。"""
        rebuilt: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
        for idx, obs in enumerate(self.buffer):
            rebuilt[obs.source.value][obs.metric].append(idx)
        self.index = rebuilt

    def _candidate_indices(self, source: Optional[str], metric: Optional[str]) -> Optional[List[int]]:
        """
        根据 source/metric 从 index 中获取候选下标。

        Returns:
            None 表示不使用索引（退化为全量扫描）。
        """
        if source is None and metric is None:
            return None

        if source is not None and metric is not None:
            return list(self.index.get(source, {}).get(metric, []))

        if source is not None:
            by_metric = self.index.get(source, {})
            merged: List[int] = []
            for idx_list in by_metric.values():
                merged.extend(idx_list)
            merged.sort()
            return merged

        # 仅 metric 过滤：跨 source 汇总同名 metric 下标
        merged = []
        for by_metric in self.index.values():
            merged.extend(by_metric.get(metric or "", []))
        merged.sort()
        return merged

    def _normalize_source(self, source: Optional[str]) -> Optional[str]:
        """将来源参数规范化为索引键格式（小写字符串）。"""
        if source is None:
            return None
        if hasattr(source, "value"):
            return str(getattr(source, "value")).lower()
        return str(source).lower()

    def _should_drop(self, obs: Observation) -> bool:
        """
        高频消息丢弃策略钩子。

        当前不启用任何策略，始终保留数据。
        后续可由上层 Engine 扩展调用或覆写策略。
        """
        _ = obs
        return False
