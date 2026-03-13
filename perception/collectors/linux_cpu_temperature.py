"""Linux CPU 温度采集 Collector。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from uuid import uuid4

import psutil

from ..models import Observation, SourceType
from .base import BaseCollector


class LinuxCpuTemperatureCollector(BaseCollector):
    """在 Linux 上采集 CPU 温度。"""

    PSUTIL_CPU_HINTS = ("cpu", "core", "package", "k10temp", "zenpower", "x86_pkg_temp")
    SYSFS_CPU_HINTS = ("cpu", "package", "tctl", "tdie", "coretemp", "k10temp")

    def __init__(self, interval: int) -> None:
        super().__init__(
            name="linux_cpu_temperature",
            interval=interval,
            required_capabilities={"cpu", "os:linux"},
        )

    def should_enable(self, system_info: Dict[str, Any]) -> bool:
        """仅在 Linux 且存在可用温度源时启用。"""
        os_name = str(system_info.get("os", "") or "").strip().lower()
        if os_name != "linux":
            return False
        return bool(self._collect_psutil(datetime.now()) or self._collect_sysfs(datetime.now()))

    def collect(self) -> Iterable[Observation]:
        """采集当前 CPU 温度。"""
        timestamp = datetime.now()
        observations = self._collect_psutil(timestamp)
        if observations:
            return observations
        return self._collect_sysfs(timestamp)

    def _collect_psutil(self, timestamp: datetime) -> List[Observation]:
        observations: List[Observation] = []
        try:
            sensors = psutil.sensors_temperatures(fahrenheit=False) or {}
        except (AttributeError, NotImplementedError):
            return observations
        except Exception:
            return observations

        for chip, entries in sensors.items():
            chip_lower = str(chip or "").strip().lower()
            if chip_lower and not any(hint in chip_lower for hint in self.PSUTIL_CPU_HINTS):
                continue
            for index, entry in enumerate(entries):
                current = getattr(entry, "current", None)
                if current is None:
                    continue
                label = str(getattr(entry, "label", "") or "").strip()
                if label:
                    label_lower = label.lower()
                    if not any(hint in label_lower for hint in self.SYSFS_CPU_HINTS):
                        continue
                observations.append(
                    self._build_observation(
                        metric="cpu.temperature_c",
                        value=float(current),
                        source=SourceType.CPU,
                        timestamp=timestamp,
                        tags={
                            "chip": chip,
                            "label": label,
                            "sensor_index": index,
                            "backend": "psutil",
                        },
                    )
                )
        return observations

    def _collect_sysfs(self, timestamp: datetime) -> List[Observation]:
        observations: List[Observation] = []
        observations.extend(self._collect_hwmon(timestamp))
        observations.extend(self._collect_thermal_zones(timestamp))
        return observations

    def _collect_hwmon(self, timestamp: datetime) -> List[Observation]:
        observations: List[Observation] = []
        for hwmon_dir in Path("/sys/class/hwmon").glob("hwmon*"):
            chip_name = self._read_text(hwmon_dir / "name")
            chip_lower = chip_name.lower()
            if chip_lower and not any(hint in chip_lower for hint in self.SYSFS_CPU_HINTS):
                continue
            for temp_input in hwmon_dir.glob("temp*_input"):
                raw = self._read_text(temp_input)
                value_c = self._millidegree_to_celsius(raw)
                if value_c is None:
                    continue
                temp_name = temp_input.stem.replace("_input", "")
                label = self._read_text(hwmon_dir / f"{temp_name}_label")
                observations.append(
                    self._build_observation(
                        metric="cpu.temperature_c",
                        value=value_c,
                        source=SourceType.CPU,
                        timestamp=timestamp,
                        tags={
                            "chip": chip_name,
                            "label": label,
                            "sensor": temp_name,
                            "backend": "sysfs.hwmon",
                        },
                    )
                )
        return observations

    def _collect_thermal_zones(self, timestamp: datetime) -> List[Observation]:
        observations: List[Observation] = []
        for zone_dir in Path("/sys/class/thermal").glob("thermal_zone*"):
            zone_type = self._read_text(zone_dir / "type")
            zone_lower = zone_type.lower()
            if zone_lower and not any(hint in zone_lower for hint in self.SYSFS_CPU_HINTS):
                continue
            value_c = self._millidegree_to_celsius(self._read_text(zone_dir / "temp"))
            if value_c is None:
                continue
            observations.append(
                self._build_observation(
                    metric="cpu.temperature_c",
                    value=value_c,
                    source=SourceType.CPU,
                    timestamp=timestamp,
                    tags={
                        "zone": zone_dir.name,
                        "label": zone_type,
                        "backend": "sysfs.thermal",
                    },
                )
            )
        return observations

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @staticmethod
    def _millidegree_to_celsius(raw: str) -> float | None:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        if abs(value) >= 1000.0:
            value = value / 1000.0
        return value

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
