"""感知层枚举定义。"""

from enum import Enum


class SourceType(str, Enum):
    """观测来源类型。"""

    CPU = "cpu"  # CPU 相关指标
    MEMORY = "memory"  # 内存相关指标
    PROCESS = "process"  # 进程级指标
    FILESYSTEM = "filesystem"  # 文件系统指标
    NETWORK = "network"  # 网络指标
    GPU = "gpu"  # GPU 相关指标


class TrendDirection(str, Enum):
    """趋势方向与变化形态。"""

    UP = "up"  # 上升趋势
    DOWN = "down"  # 下降趋势
    STABLE = "stable"  # 平稳趋势
    RAPID_CHANGE = "rapid_change"  # 短时间内快速变化
    RAPID_RISE = "rapid_rise"  # 短时间内快速上升
    RAPID_DROP = "rapid_drop"  # 短时间内快速下降
    LONG_SATURATION = "long_saturation"  # 长时间高位占满/饱和


class EventLevel(str, Enum):
    """事件级别。"""

    INFO = "info"  # 普通信息事件
    WARNING = "warning"  # 告警事件
    CRITICAL = "critical"  # 严重事件
