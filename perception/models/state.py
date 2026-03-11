"""系统状态数据模型。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from .enums import SourceType


@dataclass
class State:
    """当前系统状态。"""

    metric: str  # 指标名称
    value: Any  # 当前值
    source: SourceType  # 数据来源
    timestamp: datetime  # 状态时间戳
    tags: Dict[str, Any]  # 附加标签