"""Reflex 接口层统一导出。"""

from .collector import BaseCollector
from .sink import RecordSink

__all__ = ["BaseCollector", "RecordSink"]
