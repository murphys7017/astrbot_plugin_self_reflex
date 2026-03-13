"""Windows CPU 温度采集 Collector。"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from typing import Any, Dict, Iterable, List
from uuid import uuid4

from ..models import Observation, SourceType
from .base import BaseCollector


class WindowsCpuTemperatureCollector(BaseCollector):
    """通过 Windows WMI/CIM 温度源采集 CPU 温度。"""

    POWERSHELL_COMMAND = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "$items = Get-CimInstance -Namespace root/wmi "
            "-ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | "
            "Select-Object InstanceName, CurrentTemperature; "
            "if ($null -eq $items) { '[]' } else { $items | ConvertTo-Json -Compress }"
        ),
    ]

    def __init__(self, interval: int, command_timeout_seconds: float = 3.0) -> None:
        super().__init__(
            name="windows_cpu_temperature",
            interval=interval,
            required_capabilities={"cpu", "os:windows"},
        )
        self._command_timeout_seconds = max(0.5, float(command_timeout_seconds))

    def should_enable(self, system_info: Dict[str, Any]) -> bool:
        """仅在 Windows 且存在可读温度源时启用。"""
        os_name = str(system_info.get("os", "") or "").strip().lower()
        if os_name != "windows":
            return False
        return bool(self._query_temperature_rows())

    def collect(self) -> Iterable[Observation]:
        """采集当前 Windows CPU 温度。"""
        timestamp = datetime.now()
        observations: List[Observation] = []
        for row in self._query_temperature_rows():
            value_c = self._tenths_kelvin_to_celsius(row.get("CurrentTemperature"))
            if value_c is None:
                continue
            instance_name = str(row.get("InstanceName", "") or "").strip()
            observations.append(
                self._build_observation(
                    metric="cpu.temperature_c",
                    value=value_c,
                    source=SourceType.CPU,
                    timestamp=timestamp,
                    tags={
                        "instance_name": instance_name,
                        "backend": "windows.cim",
                    },
                )
            )
        return observations

    def _query_temperature_rows(self) -> List[Dict[str, Any]]:
        try:
            proc = subprocess.run(
                self.POWERSHELL_COMMAND,
                capture_output=True,
                text=True,
                timeout=self._command_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if proc.returncode != 0:
            return []

        text = str(proc.stdout or "").strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @staticmethod
    def _tenths_kelvin_to_celsius(value: Any) -> float | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if numeric <= 0:
            return None
        return round((numeric / 10.0) - 273.15, 2)

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
