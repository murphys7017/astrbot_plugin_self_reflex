"""系统趋势数据模型。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from .enums import TrendDirection


@dataclass
class Trend:
    """系统指标趋势。"""

    metric: str  # 指标名称
    start_time: datetime  # 趋势窗口起始时间
    end_time: datetime  # 趋势窗口结束时间
    direction: TrendDirection  # 趋势方向/形态
    slope: float  # 趋势斜率
    samples: int  # 样本数量
    series_key: str  # 趋势序列唯一标识
    series_tags: Dict[str, Any]  # 趋势序列身份标签
