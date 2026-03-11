"""Reflex 记录输出端接口定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.types import ReflexRecord


class RecordSink(ABC):
    """记录下沉（输出）抽象接口。"""

    @abstractmethod
    async def emit(self, record: ReflexRecord) -> None:
        """异步输出一条 Reflex 记录。"""
