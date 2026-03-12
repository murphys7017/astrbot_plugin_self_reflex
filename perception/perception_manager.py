"""Perception 系统总调度管理器。"""

import asyncio
import os
import platform
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from importlib import import_module
from typing import Any, Awaitable, Callable, Dict, List, Optional

from astrbot.api import logger
from .collectors import BaseCollector
from .events import EventManager
from .manager import CollectorManager
from .models import Trend
from .reflex import ReflexEngine, ReflexSignal
from .stream import ObservationStream
from .trend import BaseTrendStrategy, TrendEngine


DEFAULT_CONFIG: Dict[str, Any] = {
    "stream_window_seconds": 300,
    "collector_tick_interval": 0.5,
    "trend_interval_seconds": 30.0,
    "fallback_trend_window_seconds": 30.0,
    "collector_default_interval_seconds": 5,
    "collector_rate_limit": 200,
    "collector_no_data_threshold": 50,
    "collector_timeout_seconds": 3,
    "collector_offline_factor": 3,
    "psutil_top_processes": 5,
    "event_queue_size": 1000,
    "reflex_batch_size": 10,
    "reflex_batch_timeout": 5.0,
    "reflex_rate_limit": 10.0,
}


class PerceptionManager:
    """Perception 模块编排器，负责连接与调度子系统。"""

    def __init__(
        self,
        llm_generate: Callable[[str], Awaitable[str]],
        config: Optional[dict] = None,
    ) -> None:
        cfg = dict(DEFAULT_CONFIG)
        if config:
            cfg.update(config)
        self.config = cfg
        logger.info("PerceptionManager initializing")

        # 统一事件总线：确保 Collector / Trend / Reflex 共享同一个 EventManager。
        self.event_manager = EventManager(max_queue_size=int(cfg["event_queue_size"]))
        # ObservationStream 是全局观测缓存，TrendEngine 与 CollectorManager 共享它。
        self.stream = ObservationStream(
            time_window=timedelta(seconds=float(cfg["stream_window_seconds"]))
        )
        self.collector_manager = CollectorManager(
            stream=self.stream,
            event_manager=self.event_manager,
            default_interval=timedelta(seconds=int(cfg["collector_default_interval_seconds"])),
            rate_limit=int(cfg["collector_rate_limit"]),
            no_data_threshold=int(cfg["collector_no_data_threshold"]),
            collect_timeout=timedelta(seconds=float(cfg["collector_timeout_seconds"])),
            offline_factor=int(cfg["collector_offline_factor"]),
        )
        self.trend_engine = TrendEngine(
            stream=self.stream,
            event_manager=self.event_manager,
            fallback_window=timedelta(seconds=float(cfg["fallback_trend_window_seconds"])),
            fallback_interval=timedelta(seconds=float(cfg["trend_interval_seconds"])),
        )
        self.reflex_engine = ReflexEngine(
            event_manager=self.event_manager,
            llm_generate=llm_generate,
            batch_size=int(cfg["reflex_batch_size"]),
            batch_timeout=float(cfg["reflex_batch_timeout"]),
            rate_limit=float(cfg["reflex_rate_limit"]),
        )

        self._collector_tick_interval = float(cfg["collector_tick_interval"])
        self._trend_interval = timedelta(seconds=float(cfg["trend_interval_seconds"]))
        self._tasks: List[asyncio.Task[Any]] = []
        self._running = False
        logger.info(
            f"PerceptionManager initialized: stream_window={int(float(cfg['stream_window_seconds']))}s "
            f"collector_tick={self._collector_tick_interval} "
            f"trend_interval={self._trend_interval.total_seconds()}s "
            f"fallback_trend_window={float(cfg['fallback_trend_window_seconds'])}s"
        )

    async def start(self) -> None:
        """启动 Perception 子系统任务。"""
        if self._running:
            logger.debug("PerceptionManager start skipped: already running")
            return

        self._running = True
        self._tasks.append(
            asyncio.create_task(
                self.collector_manager.run(tick_interval=self._collector_tick_interval),
                name="perception.collector_manager",
            )
        )
        self._tasks.append(
            asyncio.create_task(
                self.trend_engine.run(interval=self._trend_interval),
                name="perception.trend_engine",
            )
        )
        self._tasks.append(
            asyncio.create_task(
                self.reflex_engine.run(),
                name="perception.reflex_engine",
            )
        )
        logger.info(f"PerceptionManager started with {len(self._tasks)} tasks")

    async def stop(self) -> None:
        """停止 Perception 子系统任务。"""
        if not self._running:
            logger.debug("PerceptionManager stop skipped: already stopped")
            return

        self.collector_manager.stop()
        self.trend_engine.stop()
        self.reflex_engine.stop()

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        self._running = False
        logger.info("PerceptionManager stopped")

    def register_collector(self, collector: BaseCollector) -> bool:
        """
        注册 Collector。

        返回：
            True: 已加载
            False: 当前系统不满足 collector 所需能力，未加载
        """
        if not self._can_load_collector(collector):
            logger.info(f"Collector skipped due to missing capabilities: {collector.name}")
            return False

        self.collector_manager.register(collector)
        logger.info(f"Collector accepted by PerceptionManager: {collector.name}")
        return True

    def load_collector_plugin(self, module_path: str, class_name: str, *args: object, **kwargs: object) -> bool:
        """
        加载 Collector 插件并按系统能力判断是否注册。

        返回：
            True: 已加载
            False: 未满足能力要求
        """
        module = import_module(module_path)
        collector_cls = getattr(module, class_name)
        collector = collector_cls(*args, **kwargs)
        if not isinstance(collector, BaseCollector):
            raise TypeError(f"{module_path}.{class_name} 不是 BaseCollector 子类")
        logger.debug(f"Collector plugin instantiated: {module_path}.{class_name}")
        return self.register_collector(collector)

    def register_trend_strategy(self, strategy: BaseTrendStrategy) -> None:
        """注册趋势策略。"""
        self.trend_engine.register_strategy(strategy)
        logger.info(f"Trend strategy registered: metric={strategy.metric}")

    async def get_signal(self) -> ReflexSignal:
        """获取一条 Reflex 输出信号。"""
        logger.debug("PerceptionManager waiting for signal")
        return await self.reflex_engine.get_signal()

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统整体运行状态。"""
        # 该接口用于命令面板/工具函数读取运行状态，需返回可序列化结构。
        return {
            "running": self._running,
            "collectors_count": len(self.collector_manager.collectors),
            "collector_states": {
                name: self._to_json_safe(asdict(state))
                for name, state in self.collector_manager.states.items()
            },
            "stream_buffer_size": len(self.stream.buffer),
            "trend_count": len(self.trend_engine.trends),
            "event_queue_size": self.event_manager.queue().qsize(),
            "signal_queue_size": self.reflex_engine.signal_queue.qsize(),
            "tasks": [
                {
                    "name": task.get_name(),
                    "done": task.done(),
                    "cancelled": task.cancelled(),
                }
                for task in self._tasks
            ],
        }

    def get_current_system_info(self) -> Dict[str, Any]:
        """获取当前宿主系统信息与能力标签。"""
        system_name = platform.system().lower()
        capabilities = {"cpu", "memory", "process", "filesystem", "network", f"os:{system_name}"}
        if shutil.which("nvidia-smi"):
            capabilities.add("gpu")

        return {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
            "cwd": os.getcwd(),
            "capabilities": sorted(capabilities),
        }

    def get_trends(self, metric: Optional[str] = None, limit: Optional[int] = None) -> List[Trend]:
        """获取已分析趋势列表，支持按 metric 过滤与数量限制。"""
        trends = self.trend_engine.trends
        if metric is not None:
            trends = [trend for trend in trends if trend.metric == metric]

        if limit is None:
            return list(trends)
        if limit <= 0:
            return []
        return list(trends[-limit:])

    def get_latest_trend(self, metric: Optional[str] = None) -> Optional[Trend]:
        """获取最新一条趋势。"""
        trends = self.get_trends(metric=metric, limit=1)
        if not trends:
            return None
        return trends[0]

    def _can_load_collector(self, collector: BaseCollector) -> bool:
        """判断当前系统是否满足 collector 的能力要求。"""
        required = set(getattr(collector, "required_capabilities", set()) or set())
        if not required:
            return True
        current = set(self.get_current_system_info()["capabilities"])
        logger.debug(
            f"Collector capability check: name={collector.name} "
            f"required={sorted(required)} current={sorted(current)}"
        )
        return required.issubset(current)

    def _to_json_safe(self, value: Any) -> Any:
        """将常见 Python 对象转换为可 JSON 序列化结构。"""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: self._to_json_safe(val) for key, val in value.items()}
        if isinstance(value, list):
            return [self._to_json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._to_json_safe(item) for item in value]
        return value
