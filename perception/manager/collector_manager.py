"""异步 CollectorManager：负责 Collector 调度、状态管理与事件上报。"""

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from importlib import import_module
from typing import Dict, Iterable, List, Optional

from perception.collectors import BaseCollector
from perception.events import EventManager
from perception.models import Event, EventLevel, Observation
from perception.stream import ObservationStream


@dataclass
class CollectorState:
    """Collector 运行状态。"""

    name: str
    registered_at: datetime = field(default_factory=datetime.now)
    first_run_at: Optional[datetime] = None
    last_run: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_push: Optional[datetime] = None
    error_count: int = 0
    consecutive_no_data: int = 0
    status: str = "RUNNING"  # RUNNING / ERROR / OFFLINE


class CollectorManager:
    """
    异步 Collector 管理器。

    职责：
    1. 管理 Collector 生命周期（注册、注销、插件加载）
    2. 按 Collector interval 异步调度 collect()
    3. 将 Observation 推送至 ObservationStream
    4. 维护健康状态并上报异常/超时/离线事件
    """

    collectors: Dict[str, BaseCollector]
    states: Dict[str, CollectorState]
    stream: ObservationStream
    default_interval: timedelta
    rate_limit: int
    event_manager: EventManager
    event_queue: "asyncio.Queue[Event]"

    def __init__(
        self,
        stream: ObservationStream,
        event_manager: EventManager,
        default_interval: timedelta = timedelta(seconds=5),
        rate_limit: int = 200,
        no_data_threshold: int = 50,
        collect_timeout: timedelta = timedelta(seconds=3),
        offline_factor: int = 3,
    ) -> None:
        """
        初始化 CollectorManager。

        Args:
            stream: Observation 总线。
            event_manager: 统一事件管理器。
            default_interval: 默认采集间隔。
            rate_limit: 每次执行单个 collector 时最多推送的 Observation 数量，<=0 表示不限制。
            no_data_threshold: 连续空 Observation 触发 NoData 事件阈值。
            collect_timeout: 单个 collect() 的超时阈值。
            offline_factor: 超过 interval * offline_factor 未成功采集则标记 OFFLINE。
        """
        self.collectors = {}
        self.states = {}
        self.stream = stream
        self.default_interval = default_interval
        self.rate_limit = rate_limit
        self.no_data_threshold = max(1, no_data_threshold)
        self.collect_timeout = collect_timeout
        self.offline_factor = max(2, offline_factor)
        self.event_manager = event_manager
        self.event_queue = self.event_manager.queue()
        self._running = False

    def register(self, collector: BaseCollector) -> None:
        """注册 Collector。"""
        if collector.name in self.collectors:
            raise ValueError(f"collector '{collector.name}' 已注册")

        self.collectors[collector.name] = collector
        self.states[collector.name] = CollectorState(name=collector.name)

    def unregister(self, collector_name: str) -> None:
        """注销 Collector。"""
        self.collectors.pop(collector_name, None)
        self.states.pop(collector_name, None)

    def load_plugin(self, module_path: str, class_name: str, *args: object, **kwargs: object) -> BaseCollector:
        """
        通过模块路径加载 Collector 插件并注册。

        Args:
            module_path: Python 模块路径。
            class_name: Collector 类名。
            *args: Collector 初始化位置参数。
            **kwargs: Collector 初始化关键字参数。
        """
        module = import_module(module_path)
        collector_cls = getattr(module, class_name)
        collector = collector_cls(*args, **kwargs)
        if not isinstance(collector, BaseCollector):
            raise TypeError(f"{module_path}.{class_name} 不是 BaseCollector 子类")
        self.register(collector)
        return collector

    async def run(self, tick_interval: float = 0.5) -> None:
        """
        启动自调度循环。

        Args:
            tick_interval: 调度心跳间隔（秒）。
        """
        self._running = True
        try:
            while self._running:
                await self.tick()
                await asyncio.sleep(tick_interval)
        finally:
            self._running = False

    def stop(self) -> None:
        """停止 run() 循环。"""
        self._running = False

    async def tick(self) -> None:
        """
        异步调度所有到期 Collector。

        - 根据各自 interval 调用 collect()
        - push Observation 到 stream
        - 捕获异常并上报事件
        """
        now = datetime.now()
        tasks: List[asyncio.Task[None]] = []

        for collector in self.collectors.values():
            state = self.states.get(collector.name)
            if state is None:
                continue

            interval = self._get_interval(collector)
            if state.last_run is None or now - state.last_run >= interval:
                tasks.append(asyncio.create_task(self._run_collector(collector)))

        if tasks:
            await asyncio.gather(*tasks)

        await self._monitor_health()

    async def _run_collector(self, collector: BaseCollector) -> None:
        """
        异步执行单个 Collector.collect()。

        - 应用 rate limit
        - push 到 ObservationStream
        - 更新 CollectorState
        - 异常时触发 CollectorErrorEvent
        """
        state = self.states.get(collector.name)
        if state is None:
            return

        now = datetime.now()
        if state.first_run_at is None:
            state.first_run_at = now
        state.last_run = now

        try:
            observations = await self._collect_observations(collector)
            limited = self.apply_rate_limit(observations)
            if limited:
                self.stream.push_many(limited)
                state.last_push = datetime.now()
                state.consecutive_no_data = 0
            else:
                state.consecutive_no_data += 1
                if state.consecutive_no_data >= self.no_data_threshold:
                    await self._emit_event(
                        event_type="CollectorNoDataEvent",
                        level=EventLevel.WARNING,
                        message=f"collector '{collector.name}' 连续空采集达到阈值",
                        context={
                            "collector": collector.name,
                            "consecutive_no_data": state.consecutive_no_data,
                            "threshold": self.no_data_threshold,
                        },
                    )
                    state.consecutive_no_data = 0

            state.last_success = datetime.now()
            state.error_count = 0
            state.status = "RUNNING"
        except asyncio.TimeoutError:
            state.error_count += 1
            state.status = "ERROR"
            await self._emit_event(
                event_type="CollectorTimeoutEvent",
                level=EventLevel.WARNING,
                message=f"collector '{collector.name}' collect 超时",
                context={"collector": collector.name, "timeout_seconds": self.collect_timeout.total_seconds()},
            )
        except Exception as exc:
            state.error_count += 1
            state.status = "ERROR"
            await self._emit_event(
                event_type="CollectorErrorEvent",
                level=EventLevel.CRITICAL,
                message=f"collector '{collector.name}' 执行异常: {exc}",
                context={"collector": collector.name, "error": repr(exc)},
            )

    async def _monitor_health(self) -> None:
        """
        异步监控 Collector 状态。

        - 未按 interval 成功采集 -> CollectorTimeoutEvent
        - 连续超时/异常导致长时间不可用 -> CollectorOfflineEvent
        """
        now = datetime.now()
        for name, collector in self.collectors.items():
            state = self.states.get(name)
            if state is None:
                continue

            interval = self._get_interval(collector)
            reference_time = state.last_success or state.first_run_at or state.registered_at
            elapsed = now - reference_time

            if elapsed > interval and state.status == "RUNNING":
                state.status = "ERROR"
                await self._emit_event(
                    event_type="CollectorTimeoutEvent",
                    level=EventLevel.WARNING,
                    message=f"collector '{name}' 超过 interval 未成功上报",
                    context={
                        "collector": name,
                        "elapsed_seconds": elapsed.total_seconds(),
                        "interval_seconds": interval.total_seconds(),
                    },
                )

            if elapsed > interval * self.offline_factor and state.status != "OFFLINE":
                state.status = "OFFLINE"
                await self._emit_event(
                    event_type="CollectorOfflineEvent",
                    level=EventLevel.CRITICAL,
                    message=f"collector '{name}' 长时间未恢复，标记为 OFFLINE",
                    context={
                        "collector": name,
                        "elapsed_seconds": elapsed.total_seconds(),
                        "offline_threshold_seconds": (interval * self.offline_factor).total_seconds(),
                    },
                )

    def apply_rate_limit(self, observations: Iterable[Observation]) -> List[Observation]:
        """
        对高频 Observation 进行限流。

        当前策略：保留前 N 条（N=rate_limit）。若 rate_limit <= 0 则不过滤。
        """
        obs_list = list(observations)
        if self.rate_limit <= 0:
            return obs_list
        return obs_list[: self.rate_limit]

    def get_state(self, collector_name: str) -> Optional[CollectorState]:
        """获取单个 Collector 状态。"""
        return self.states.get(collector_name)

    async def _collect_observations(self, collector: BaseCollector) -> List[Observation]:
        """执行 collect() 并统一转换为 Observation 列表。"""
        if inspect.iscoroutinefunction(collector.collect):
            resolved = await asyncio.wait_for(
                collector.collect(),
                timeout=self.collect_timeout.total_seconds(),
            )
            return list(resolved or [])

        # 同步 collect() 整体在线程中执行，避免阻塞事件循环。
        resolved_sync = await asyncio.wait_for(
            asyncio.to_thread(self._collect_sync, collector),
            timeout=self.collect_timeout.total_seconds(),
        )
        return list(resolved_sync or [])

    def _get_interval(self, collector: BaseCollector) -> timedelta:
        """获取 Collector 有效调度间隔。"""
        interval_seconds = getattr(collector, "interval", 0) or int(self.default_interval.total_seconds())
        return timedelta(seconds=max(1, int(interval_seconds)))

    async def _emit_event(
        self,
        event_type: str,
        level: EventLevel,
        message: str,
        context: Optional[Dict[str, object]] = None,
    ) -> None:
        """向事件队列投递事件。"""
        event = Event(
            type=event_type,
            level=level,
            message=message,
            timestamp=datetime.now(),
            context=context or {},
        )
        await self.event_manager.submit_event(event)

    @staticmethod
    def _collect_sync(collector: BaseCollector) -> Iterable[Observation]:
        """在线程中执行同步 collect()，并返回结果。"""
        return collector.collect()
