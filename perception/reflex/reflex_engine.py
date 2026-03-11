"""Reflex 主引擎。"""

import asyncio
from typing import Awaitable, Callable, List, Optional

from perception.events import EventManager
from perception.models import Event
from perception.reflex.decision_parser import DecisionParser, ReflexSignal
from perception.reflex.prompt_builder import PromptBuilder


class ReflexEngine:
    """从事件流批量构建 Prompt，调用 LLM 并输出 ReflexSignal。"""

    def __init__(
        self,
        event_manager: EventManager,
        llm_generate: Callable[[str], Awaitable[str]],
        batch_size: int = 10,
        batch_timeout: float = 5.0,
        rate_limit: float = 10.0,
    ) -> None:
        self.event_manager = event_manager
        self.llm_generate = llm_generate
        self.batch_size = max(1, batch_size)
        self.batch_timeout = max(0.1, batch_timeout)
        self.rate_limit = max(0.0, rate_limit)
        self.prompt_builder = PromptBuilder()
        self.decision_parser = DecisionParser()
        self.signal_queue: "asyncio.Queue[ReflexSignal]" = asyncio.Queue()
        self._last_call_time: Optional[float] = None
        self._running = False

    async def _collect_batch(self) -> List[Event]:
        """
        采集一批事件。

        - 最多收集 batch_size 条
        - 首条事件无超时阻塞等待
        - 收到首条后最多再等待 batch_timeout 收集后续事件
        """
        while self._running:
            try:
                first_event = await asyncio.wait_for(
                    self.event_manager.get(),
                    timeout=self.batch_timeout,
                )
                events: List[Event] = [first_event]
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

        return events

    async def _rate_limit_check(self) -> None:
        """保证两次 LLM 调用最少间隔 rate_limit 秒。"""
        if self._last_call_time is None or self.rate_limit <= 0:
            return

        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_call_time
        wait_time = self.rate_limit - elapsed
        if wait_time > 0:
            await asyncio.sleep(wait_time)

    async def run(self) -> None:
        """Reflex 主循环。"""
        self._running = True
        while self._running:
            events = await self._collect_batch()
            if not events:
                continue
            prompt = self.prompt_builder.build(events)

            await self._rate_limit_check()
            try:
                llm_text = await self.llm_generate(prompt)
                signal = self.decision_parser.parse(llm_text, events)
            except Exception as exc:
                signal = ReflexSignal(
                    push=False,
                    summary="",
                    reason=f"llm_call_failed: {exc}",
                    events=events,
                )
            finally:
                self._last_call_time = asyncio.get_running_loop().time()

            if signal.push:
                await self.signal_queue.put(signal)

    def stop(self) -> None:
        """停止主循环。"""
        self._running = False

    async def get_signal(self) -> ReflexSignal:
        """获取一条 Reflex 信号。"""
        return await self.signal_queue.get()
