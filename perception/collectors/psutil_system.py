"""基于 psutil 的宿主机系统总览 Collector。"""

import os
from datetime import datetime
from typing import Any, Dict, Iterable, List
from uuid import uuid4

import psutil

from ..models import Observation, SourceType
from .base import BaseCollector


class PsutilSystemCollector(BaseCollector):
    """采集宿主机总览指标与 Top N 进程快照。"""

    def __init__(self, interval: int, top_processes: int = 5) -> None:
        super().__init__(
            name="psutil_system",
            interval=interval,
            required_capabilities={"cpu", "memory", "process"},
        )
        self.top_processes = max(1, int(top_processes))
        self._disk_path = os.path.abspath(os.getcwd())
        psutil.cpu_percent(interval=None)

    def collect(self) -> Iterable[Observation]:
        """采集当前宿主机状态。"""
        timestamp = datetime.now()
        observations: List[Observation] = []

        observations.extend(self._collect_host_metrics(timestamp))
        observations.extend(self._collect_top_process_metrics(timestamp))
        return observations

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

    def _collect_top_process_metrics(self, timestamp: datetime) -> List[Observation]:
        """采集按内存占用排序的 Top N 进程指标。"""
        ranked = self._get_ranked_processes()
        observations: List[Observation] = []

        for rank, proc_info in enumerate(ranked[: self.top_processes], start=1):
            base_tags = {
                "pid": proc_info["pid"],
                "name": proc_info["name"],
                "status": proc_info["status"],
                "rank": rank,
            }
            observations.append(
                self._build_observation(
                    "process.top.memory_percent",
                    proc_info["memory_percent"],
                    SourceType.PROCESS,
                    timestamp,
                    tags=base_tags,
                )
            )
            observations.append(
                self._build_observation(
                    "process.top.cpu_percent",
                    proc_info["cpu_percent"],
                    SourceType.PROCESS,
                    timestamp,
                    tags=base_tags,
                )
            )
            observations.append(
                self._build_observation(
                    "process.top.rss_bytes",
                    proc_info["rss_bytes"],
                    SourceType.PROCESS,
                    timestamp,
                    tags=base_tags,
                )
            )

        return observations

    def _get_ranked_processes(self) -> List[Dict[str, Any]]:
        """采集进程快照并按内存占比排序。"""
        processes: List[Dict[str, Any]] = []
        for process in psutil.process_iter(["pid", "name", "status", "memory_percent"]):
            try:
                info = process.info
                memory_percent = float(info.get("memory_percent") or 0.0)
                cpu_percent = float(process.cpu_percent(interval=None) or 0.0)
                memory_info = process.memory_info()
                processes.append(
                    {
                        "pid": int(info.get("pid") or 0),
                        "name": str(info.get("name") or "unknown"),
                        "status": str(info.get("status") or "unknown"),
                        "memory_percent": memory_percent,
                        "cpu_percent": cpu_percent,
                        "rss_bytes": int(getattr(memory_info, "rss", 0) or 0),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        processes.sort(key=lambda item: item["memory_percent"], reverse=True)
        return processes

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
