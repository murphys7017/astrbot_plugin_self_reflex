"""原始观测数据模型。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from .enums import SourceType


@dataclass
class Observation:
    """原始系统观测数据。"""

    id: str  # 唯一观测 ID
    source: SourceType  # 观测来源
    metric: str  # 指标名称
    value: Any  # 观测值
    timestamp: datetime  # 采集时间
    tags: Dict[str, Any]  # 附加标签
