"""Reflex 记录采集器接口定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from ..models.types import ReflexRecord


@dataclass(slots=True)
class BaseCollector(ABC):
    """采集器抽象基类。"""

    # 采集器名称，用于标识数据来源
    name: str
    # 采集周期（秒）
    interval: float

    @abstractmethod
    def start(self) -> None:
        """启动采集器生命周期。"""

    @abstractmethod
    def stop(self) -> None:
        """停止采集器生命周期。"""

    @abstractmethod
    def collect(self) -> List[ReflexRecord]:
        """采集一批 Reflex 记录。"""
