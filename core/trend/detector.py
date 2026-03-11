"""最小趋势检测函数。"""

from __future__ import annotations


def detect_sustained_high(values: list[float], threshold: float = 80) -> bool:
    """最近 3 个样本都高于阈值则判定为持续高位。"""
    if len(values) < 3:
        return False
    return all(value >= threshold for value in values[-3:])


def detect_rising_fast(values: list[float], delta: float = 20) -> bool:
    """窗口首尾差值上升超过 delta 则判定快速上升。"""
    if len(values) < 2:
        return False
    return (values[-1] - values[0]) >= delta


def detect_falling_fast(values: list[float], delta: float = 20) -> bool:
    """窗口首尾差值下降超过 delta 则判定快速下降。"""
    if len(values) < 2:
        return False
    return (values[0] - values[-1]) >= delta


def detect_burst(values: list[float], delta: float = 30) -> bool:
    """相邻两个样本突变超过 delta 则判定突发波动。"""
    if len(values) < 2:
        return False
    return abs(values[-1] - values[-2]) >= delta

