"""基于 psutil 的宿主机系统总览 Collector。"""

import os
from datetime import datetime
from typing import Any, Dict, Iterable, List
from uuid import uuid4

import psutil

from ..models import Observation, SourceType
from .base import BaseCollector


class PsutilSystemCollector(BaseCollector):
    """采集宿主机总览指标。"""

    def __init__(self, interval: int, top_processes: int = 5) -> None:
        super().__init__(
            name="psutil_system",
            interval=interval,
            required_capabilities={"cpu", "memory", "process"},
        )
        _ = top_processes
        self._disk_path = os.path.abspath(os.getcwd())
        psutil.cpu_percent(interval=None)

    def should_enable(self, system_info: Dict[str, Any]) -> bool:
        """默认宿主机采集器在常见桌面/服务器平台均启用。"""
        os_name = str(system_info.get("os", "") or "").strip().lower()
        return os_name in {"windows", "linux", "darwin"}

    def collect(self) -> Iterable[Observation]:
        """采集当前宿主机状态。"""
        timestamp = datetime.now()
        return self._collect_host_metrics(timestamp)

    def _collect_host_metrics(self, timestamp: datetime) -> List[Observation]:
        """采集宿主机级别指标。"""
        virtual_memory = psutil.virtual_memory()
        swap_memory = psutil.swap_memory()
        disk_usage = psutil.disk_usage(self._disk_path)
        net_io = psutil.net_io_counters()
        process_count = len(psutil.pids())

        return [
            self._build_observation("cpu.percent", psutil.cpu_percent(interval=None), SourceType.CPU, timestamp),
            self._build_observation("memory.percent", virtual_memory.percent, SourceType.MEMORY, timestamp),
            self._build_observation("memory.used_bytes", virtual_memory.used, SourceType.MEMORY, timestamp),
            self._build_observation("memory.available_bytes", virtual_memory.available, SourceType.MEMORY, timestamp),
            self._build_observation("swap.percent", swap_memory.percent, SourceType.MEMORY, timestamp),
            self._build_observation("swap.used_bytes", swap_memory.used, SourceType.MEMORY, timestamp),
            self._build_observation("disk.percent", disk_usage.percent, SourceType.FILESYSTEM, timestamp),
            self._build_observation("disk.used_bytes", disk_usage.used, SourceType.FILESYSTEM, timestamp),
            self._build_observation("disk.free_bytes", disk_usage.free, SourceType.FILESYSTEM, timestamp),
            self._build_observation("network.bytes_sent", net_io.bytes_sent, SourceType.NETWORK, timestamp),
            self._build_observation("network.bytes_recv", net_io.bytes_recv, SourceType.NETWORK, timestamp),
            self._build_observation("process.count", process_count, SourceType.PROCESS, timestamp),
        ]

    def _build_observation(
        self,
        metric: str,
        value: Any,
        source: SourceType,
        timestamp: datetime,
        tags: Dict[str, Any] | None = None,
    ) -> Observation:
        """构建单条 Observation。"""
        return Observation(
            id=uuid4().hex,
            source=source,
            metric=metric,
            value=value,
            timestamp=timestamp,
            tags=dict(tags or {}),
        )
