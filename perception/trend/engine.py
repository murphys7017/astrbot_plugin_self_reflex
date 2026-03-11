"""TrendEngine：异步趋势分析调度器。"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from perception.events import EventManager
from perception.models import Event, EventLevel, Trend
from perception.stream import ObservationStream
from perception.trend.strategy import BaseTrendStrategy


class TrendEngine:
    """
    趋势分析引擎。

    职责：
    1. 按策略配置（metric + window）拉取 Observation
    2. 调用策略计算 Trend
    3. 对空数据与策略异常进行事件上报
    """

    stream: ObservationStream
    event_manager: EventManager
    event_queue: "asyncio.Queue[Event]"
    strategies: List[BaseTrendStrategy]
    trends: List[Trend]

    def __init__(self, stream: ObservationStream, event_manager: EventManager) -> None:
        self.stream = stream
        self.event_manager = event_manager
        self.event_queue = self.event_manager.queue()
        self.strategies = []
        self.trends = []
        self._running = False

    def register_strategy(self, strategy: BaseTrendStrategy) -> None:
        """注册趋势策略。"""
        self.strategies.append(strategy)

    def unregister_strategy(self, metric: str) -> None:
        """按 metric 注销策略。"""
        self.strategies = [strategy for strategy in self.strategies if strategy.metric != metric]

    async def analyze(self) -> List[Trend]:
        """
        执行一次异步分析。

        Returns:
            本轮产出的 Trend 列表。
        """
        analyzed_trends: List[Trend] = []
        for strategy in self.strategies:
            strategy_now = datetime.now()
            now_ts = strategy_now.timestamp()
            if not strategy.should_run(now_ts):
                continue

            start_time = strategy_now - strategy.window
            observations = self.stream.get_window(
                start=start_time,
                end=strategy_now,
                metric=strategy.metric,
            )
            try:
                trend = strategy.compute_trend(observations)
                if trend is not None:
                    self.submit_trend(trend)
                    analyzed_trends.append(trend)
                else:
                    await self._emit_event(
                        event_type="TrendNoDataEvent",
                        level=EventLevel.INFO,
                        message=f"metric '{strategy.metric}' 在窗口内无可用数据",
                        context={
                            "metric": strategy.metric,
                            "window_seconds": strategy.window.total_seconds(),
                            "observation_count": len(observations),
                        },
                    )
            except Exception as exc:
                await self._emit_event(
                    event_type="TrendStrategyErrorEvent",
                    level=EventLevel.WARNING,
                    message=f"metric '{strategy.metric}' 趋势策略执行失败: {exc}",
                    context={
                        "metric": strategy.metric,
                        "window_seconds": strategy.window.total_seconds(),
                        "error": repr(exc),
                    },
                )
            finally:
                strategy._last_run = now_ts

        return analyzed_trends

    def submit_trend(self, trend: Trend) -> None:
        """提交 Trend 到引擎内部结果列表（供上层消费）。"""
        self.trends.append(trend)

    async def run(self, interval: timedelta) -> None:
        """持续运行 TrendEngine，每 interval 执行一次 analyze()。"""
        self._running = True
        try:
            while self._running:
                await self.analyze()
                await asyncio.sleep(interval.total_seconds())
        finally:
            self._running = False

    def stop(self) -> None:
        """停止 run() 循环。"""
        self._running = False

    async def _emit_event(
        self,
        event_type: str,
        level: EventLevel,
        message: str,
        context: Optional[dict] = None,
    ) -> None:
        """写入趋势分析事件到 event_queue。"""
        await self.event_manager.submit_event(
            Event(
                type=event_type,
                level=level,
                message=message,
                timestamp=datetime.now(),
                context=context or {},
            )
        )
