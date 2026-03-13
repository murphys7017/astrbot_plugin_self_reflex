"""Collector 模块导出。"""

from .base import BaseCollector
from .linux_cpu_temperature import LinuxCpuTemperatureCollector
from .nvidia_gpu import NvidiaGpuCollector
from .psutil_system import PsutilSystemCollector
from .windows_cpu_temperature import WindowsCpuTemperatureCollector

__all__ = [
    "BaseCollector",
    "PsutilSystemCollector",
    "NvidiaGpuCollector",
    "LinuxCpuTemperatureCollector",
    "WindowsCpuTemperatureCollector",
]
