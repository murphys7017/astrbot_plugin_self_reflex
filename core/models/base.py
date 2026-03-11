"""Reflex 记录的基础数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BaseRecord:
    """所有 Reflex 记录共享的基础字段。"""

    # 数据来源标识，例如 collector 名称或模块名
    source: str
    # 记录产生时的时间戳（Unix 时间，秒）
    timestamp: float
