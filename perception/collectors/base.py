"""Collector 抽象接口定义。"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional, Set

from ..models import Observation


class BaseCollector(ABC):
    """Collector 抽象基类，只定义采集接口。"""

    name: str
    interval: int
    required_capabilities: Set[str]

    def __init__(
        self,
        name: str,
        interval: int,
        required_capabilities: Optional[Set[str]] = None,
    ) -> None:
        """
        初始化 Collector 基础属性。

        Args:
            name: Collector 名称。
            interval: 采集间隔（秒）。
            required_capabilities: Collector 所需的系统能力集合。
                由 PerceptionManager 根据当前系统能力决定是否加载。
        """
        self.name = name
        self.interval = interval
        self.required_capabilities = set(required_capabilities or set())

    @abstractmethod
    def should_enable(self, system_info: Dict[str, Any]) -> bool:
        """根据宿主平台信息判断当前 Collector 是否应被启用。"""
        raise NotImplementedError

    @abstractmethod
    def collect(self) -> Iterable[Observation]:
        """采集当前系统状态，并返回 Observation 列表。"""
        raise NotImplementedError
