"""系统事件数据模型。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from .enums import EventLevel


@dataclass
class Event:
    """系统事件或异常。"""

    type: str  # 事件类型
    level: EventLevel  # 事件级别
    message: str  # 事件描述信息
    timestamp: datetime  # 事件发生时间
    context: Dict[str, Any]  # 事件上下文