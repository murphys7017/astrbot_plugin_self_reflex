"""事件管理组件：统一接收并分发 Event 异步事件流。"""

import asyncio
from typing import AsyncIterator

from astrbot.api import logger
from perception.models import Event


class EventManager:
    """轻量事件管理器，只负责事件入队与出队。"""

    def __init__(self, max_queue_size: int = 1000) -> None:
        """
        初始化事件队列。

        Args:
            max_queue_size: 事件队列最大长度。
        """
        self._queue: "asyncio.Queue[Event]" = asyncio.Queue(maxsize=max_queue_size)
        logger.info(f"EventManager initialized: max_queue_size={max_queue_size}")

    async def submit_event(self, event: Event) -> None:
        """
        提交事件到队列。

        当队列已满时，先丢弃最旧事件，再写入新事件。
        """
        if self._queue.full():
            self._queue.get_nowait()
            logger.debug("EventManager queue full: dropped oldest event")
        self._queue.put_nowait(event)
        logger.debug(
            f"Event submitted: type={event.type} level={event.level.value} size={self._queue.qsize()}"
        )

    async def events(self) -> AsyncIterator[Event]:
        """持续输出事件流，供上层模块异步消费。"""
        while True:
            event = await self._queue.get()
            logger.debug(f"Event consumed from async iterator: type={event.type}")
            yield event

    async def submit(self, event: Event) -> None:
        """兼容旧接口：提交事件。"""
        await self.submit_event(event)

    async def get(self) -> Event:
        """兼容旧接口：从队列中获取一个事件。"""
        event = await self._queue.get()
        logger.debug(f"Event consumed from get(): type={event.type}")
        return event

    def queue(self) -> "asyncio.Queue[Event]":
        """返回内部事件队列，供上层模块直接消费。"""
        return self._queue
