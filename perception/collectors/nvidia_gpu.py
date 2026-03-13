"""基于 nvidia-smi 的 NVIDIA GPU Collector。"""

import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, Iterable, List
from uuid import uuid4

from ..models import Observation, SourceType
from .base import BaseCollector


class NvidiaGpuCollector(BaseCollector):
    """采集 NVIDIA GPU 的温度、利用率和显存指标。"""

    def __init__(self, interval: int, command_timeout_seconds: float = 2.0) -> None:
        super().__init__(
            name="nvidia_gpu",
            interval=interval,
            required_capabilities={"gpu"},
        )
        self._command_timeout_seconds = max(0.5, float(command_timeout_seconds))

    def should_enable(self, system_info: Dict[str, Any]) -> bool:
        """在支持的平台且可找到 nvidia-smi 时启用。"""
        os_name = str(system_info.get("os", "") or "").strip().lower()
        if os_name not in {"windows", "linux"}:
            return False
        return shutil.which("nvidia-smi") is not None

    def collect(self) -> Iterable[Observation]:
        """采集当前主机上的 NVIDIA GPU 指标。"""
        timestamp = datetime.now()
        rows = self._query_gpu_rows()
        observations: List[Observation] = []
        for row in rows:
            gpu_index = row["index"]
            name = row["name"]
            tags = {"gpu_index": gpu_index, "name": name}
            observations.append(
                self._build_observation(
                    metric="gpu.temperature_c",
                    value=row["temperature_c"],
                    source=SourceType.GPU,
                    timestamp=timestamp,
                    tags=tags,
                )
            )
            observations.append(
                self._build_observation(
                    metric="gpu.utilization_gpu_percent",
                    value=row["utilization_gpu_percent"],
                    source=SourceType.GPU,
                    timestamp=timestamp,
                    tags=tags,
                )
            )
            observations.append(
                self._build_observation(
                    metric="gpu.memory_used_mb",
                    value=row["memory_used_mb"],
                    source=SourceType.GPU,
                    timestamp=timestamp,
                    tags=tags,
                )
            )
            observations.append(
                self._build_observation(
                    metric="gpu.memory_total_mb",
                    value=row["memory_total_mb"],
                    source=SourceType.GPU,
                    timestamp=timestamp,
                    tags=tags,
                )
            )
            observations.append(
                self._build_observation(
                    metric="gpu.memory_used_percent",
                    value=row["memory_used_percent"],
                    source=SourceType.GPU,
                    timestamp=timestamp,
                    tags=tags,
                )
            )
        return observations

    def _query_gpu_rows(self) -> List[Dict[str, Any]]:
        command = [
            "nvidia-smi",
            "--query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self._command_timeout_seconds,
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip() or "<empty>"
            raise RuntimeError(f"nvidia-smi failed: rc={proc.returncode} stderr={stderr}")

        rows: List[Dict[str, Any]] = []
        for raw_line in (proc.stdout or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = [item.strip() for item in line.split(",")]
            if len(parts) < 6:
                continue
            index, name, temp, util, mem_used, mem_total = parts[:6]
            temperature_c = self._parse_float(temp)
            utilization_gpu_percent = self._parse_float(util)
            memory_used_mb = self._parse_float(mem_used)
            memory_total_mb = self._parse_float(mem_total)
            if (
                temperature_c is None
                or utilization_gpu_percent is None
                or memory_used_mb is None
                or memory_total_mb is None
            ):
                continue
            memory_used_percent = 0.0
            if memory_total_mb > 0:
                memory_used_percent = (memory_used_mb / memory_total_mb) * 100.0
            rows.append(
                {
                    "index": index,
                    "name": name,
                    "temperature_c": temperature_c,
                    "utilization_gpu_percent": utilization_gpu_percent,
                    "memory_used_mb": memory_used_mb,
                    "memory_total_mb": memory_total_mb,
                    "memory_used_percent": memory_used_percent,
                }
            )
        return rows

    @staticmethod
    def _parse_float(value: str) -> float | None:
        text = str(value or "").strip()
        if not text or text.upper() == "N/A":
            return None
        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    def _build_observation(
        self,
        metric: str,
        value: Any,
        source: SourceType,
        timestamp: datetime,
        tags: Dict[str, Any] | None = None,
    ) -> Observation:
        return Observation(
            id=uuid4().hex,
            source=source,
            metric=metric,
            value=value,
            timestamp=timestamp,
            tags=dict(tags or {}),
        )
