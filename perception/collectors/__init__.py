"""Collector 模块导出。"""

from .base import BaseCollector
from .psutil_system import PsutilSystemCollector

__all__ = ["BaseCollector", "PsutilSystemCollector"]
