"""Reflex 主引擎。"""

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

from astrbot.api import logger
from ..events import EventManager
from ..models import Event
from .decision_parser import DecisionParser, ReflexSignal
from .prompt_builder import PromptBuilder


class ReflexEngine:
    """从事件流批量构建 Prompt，调用 LLM 并输出 ReflexSignal。"""

    def __init__(
        self,
        event_manager: EventManager,
        llm_generate: Callable[[str], Awaitable[str]],
        system_state_getter: Optional[Callable[[], Dict[str, Any]]] = None,
        batch_size: int = 10,
        batch_timeout: float = 5.0,
        rate_limit: float = 10.0,
    ) -> None:
        self.event_manager = event_manager
        self.llm_generate = llm_generate
        self.system_state_getter = system_state_getter
        self.batch_size = max(1, batch_size)
        self.batch_timeout = max(0.1, batch_timeout)
        self.rate_limit = max(0.0, rate_limit)
        self.prompt_builder = PromptBuilder()
        self.decision_parser = DecisionParser()
        self.signal_queue: "asyncio.Queue[ReflexSignal]" = asyncio.Queue()
        self._last_call_time: Optional[float] = None
        self._running = False
        logger.info(
            f"ReflexEngine initialized: batch_size={self.batch_size} "
            f"batch_timeout={self.batch_timeout} rate_limit={self.rate_limit}"
        )

    async def _collect_batch(self) -> List[Event]:
        """
        采集一批事件。

        - 最多收集 batch_size 条
        - 首条事件按 batch_timeout 轮询等待（便于 stop() 快速生效）
        - 收到首条后最多再等待 batch_timeout 收集后续事件
        """
        while self._running:
            try:
                first_event = await asyncio.wait_for(
                    self.event_manager.get(),
                    timeout=self.batch_timeout,
                )
                events: List[Event] = [first_event]
                logger.debug(f"Reflex batch first event received: type={first_event.type}")
                break
            except asyncio.TimeoutError:
                continue
        else:
            return []

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.batch_timeout

        while len(events) < self.batch_size:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break

            try:
                event = await asyncio.wait_for(self.event_manager.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            events.append(event)

        logger.debug(f"Reflex batch collected: size={len(events)}")
        return events

    async def _rate_limit_check(self) -> None:
        """保证两次 LLM 调用最少间隔 rate_limit 秒。"""
        if self._last_call_time is None or self.rate_limit <= 0:
            return

        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_call_time
        wait_time = self.rate_limit - elapsed
        if wait_time > 0:
            logger.debug(f"Reflex rate limit sleep: {wait_time:.3f}s")
            await asyncio.sleep(wait_time)

    async def run(self) -> None:
        """Reflex 主循环。"""
        self._running = True
        logger.info("ReflexEngine run loop started")
        try:
            while self._running:
                events = await self._collect_batch()
                if not events:
                    continue
                system_state = self._get_system_state()
                prompt = self.prompt_builder.build(events, system_state=system_state)
                logger.debug(f"Reflex prompt built for events={len(events)}")

                await self._rate_limit_check()
                try:
                    logger.debug(f"Reflex LLM request submitting: events={len(events)} prompt_length={len(prompt)}")
                    llm_text = await self.llm_generate(prompt)
                    logger.debug(f"Reflex LLM response received: text_length={len(llm_text or '')}")
                    signal = self.decision_parser.parse(llm_text, events)
                except Exception as exc:
                    signal = ReflexSignal(
                        push=False,
                        summary="",
                        message="",
                        reason=f"llm_call_failed: {exc}",
                        level="warning",
                        events=events,
                    )
                    logger.info(f"Reflex llm call failed: {repr(exc)}")
                finally:
                    self._last_call_time = asyncio.get_running_loop().time()

                if signal.push:
                    await self.signal_queue.put(signal)
                    logger.info(f"Reflex signal queued: summary={signal.summary}")
                else:
                    logger.debug(f"Reflex signal filtered: reason={signal.reason}")
        finally:
            logger.info("ReflexEngine run loop stopped")

    def stop(self) -> None:
        """停止主循环。"""
        self._running = False
        logger.info("ReflexEngine stop requested")

    async def get_signal(self) -> ReflexSignal:
        """获取一条 Reflex 信号。"""
        return await self.signal_queue.get()

    def _get_system_state(self) -> Dict[str, Any]:
        """获取当前系统状态快照，作为 Reflex 决策上下文。"""
        if self.system_state_getter is None:
            return {}
        try:
            return dict(self.system_state_getter() or {})
        except Exception as exc:
            logger.warning(f"Reflex system_state_getter failed: {exc}")
            return {}
