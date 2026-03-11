"""事件数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import BaseRecord


@dataclass(slots=True)
class Event(BaseRecord):
    """由数据源上报的结构化事件。"""

    # 事件级别，例如 info、warning、error
    level: str
    # 事件类型，例如 threshold_breach、collector_error
    type: str
    # 人类可读的事件描述
    message: str
    # 附加上下文字段
    metadata: dict[str, Any] = field(default_factory=dict)
