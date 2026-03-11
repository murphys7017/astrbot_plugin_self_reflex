"""系统趋势数据模型。"""

from dataclasses import dataclass
from datetime import datetime

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