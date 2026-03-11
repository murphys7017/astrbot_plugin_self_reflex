import asyncio
import json
from collections import deque
from datetime import datetime
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from perception.perception_manager import PerceptionManager
from perception.reflex import ReflexSignal


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class GetSystemStatusTool(FunctionTool[AstrAgentContext]):
    """获取 Perception 系统状态的 Tool。"""

    name: str = "get_system_status"
    description: str = "Get current perception system status."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "required": [],
        }
    )
    getter: Callable[[], Dict[str, Any]] = Field(
        default_factory=lambda: (lambda: {}),
        repr=False,
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs: Any) -> ToolExecResult:
        _ = context
        _ = kwargs
        return json.dumps(self.getter(), ensure_ascii=False, default=str)


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class GetCurrentSystemInfoTool(FunctionTool[AstrAgentContext]):
    """获取当前宿主系统信息的 Tool。"""

    name: str = "get_current_system_info"
    description: str = "Get current host system information and capabilities."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "required": [],
        }
    )
    getter: Callable[[], Dict[str, Any]] = Field(
        default_factory=lambda: (lambda: {}),
        repr=False,
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs: Any) -> ToolExecResult:
        _ = context
        _ = kwargs
        return json.dumps(self.getter(), ensure_ascii=False, default=str)


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class GetRecentSignalsTool(FunctionTool[AstrAgentContext]):
    """获取近期 Reflex 信号的 Tool。"""

    name: str = "get_recent_signals"
    description: str = "Get recent reflex signals that were escalated."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "number",
                    "description": "Maximum number of recent signals to return.",
                }
            },
            "required": [],
        }
    )
    getter: Callable[[int], List[Dict[str, Any]]] = Field(
        default_factory=lambda: (lambda limit: []),
        repr=False,
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs: Any) -> ToolExecResult:
        _ = context
        limit_raw = kwargs.get("limit", 10)
        try:
            limit = max(1, int(limit_raw))
        except (TypeError, ValueError):
            limit = 10
        return json.dumps(self.getter(limit), ensure_ascii=False, default=str)


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class GetRecentEventsTool(FunctionTool[AstrAgentContext]):
    """获取近期事件摘要的 Tool。"""

    name: str = "get_recent_events"
    description: str = "Get recent event snapshots observed from reflex signals."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "number",
                    "description": "Maximum number of recent events to return.",
                }
            },
            "required": [],
        }
    )
    getter: Callable[[int], List[Dict[str, Any]]] = Field(
        default_factory=lambda: (lambda limit: []),
        repr=False,
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs: Any) -> ToolExecResult:
        _ = context
        limit_raw = kwargs.get("limit", 20)
        try:
            limit = max(1, int(limit_raw))
        except (TypeError, ValueError):
            limit = 20
        return json.dumps(self.getter(limit), ensure_ascii=False, default=str)


@register("astrbot_plugin_self_reflex", "YakumoAki", "Self Reflex perception runtime bridge", "0.1.0")
class MyPlugin(Star):
    """AstrBot 插件入口：负责将 Perception 系统接入 AstrBot。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.perception_enabled = bool(self.config.get("perception_enabled", True))
        self._notify_unified_msg_origin = str(self.config.get("notify_unified_msg_origin", "")).strip()
        self._notify_user_id = str(self.config.get("notify_user_id", "")).strip()
        self._default_provider_id = str(self.config.get("default_provider_id", "")).strip()

        self._recent_signals: Deque[Dict[str, Any]] = deque(
            maxlen=max(1, int(self.config.get("recent_signals_cache", 50)))
        )
        self._recent_events: Deque[Dict[str, Any]] = deque(
            maxlen=max(1, int(self.config.get("recent_events_cache", 200)))
        )

        self.perception = PerceptionManager(
            llm_generate=self._llm_generate_for_reflex,
            config=self._build_perception_config(),
        )
        self._signal_task: Optional[asyncio.Task[Any]] = None
        self._register_tools()

    async def initialize(self):
        """插件初始化：启动 Perception 与后台 signal loop。"""
        if not self.perception_enabled:
            logger.info("Perception is disabled by config.")
            return

        await self.perception.start()
        self._signal_task = asyncio.create_task(self._signal_loop(), name="self_reflex.signal_loop")
        logger.info("Perception system started.")

    async def terminate(self):
        """插件销毁：停止 signal loop 与 Perception。"""
        if self._signal_task is not None:
            self._signal_task.cancel()
            await asyncio.gather(self._signal_task, return_exceptions=True)
            self._signal_task = None

        if self.perception_enabled:
            await self.perception.stop()
            logger.info("Perception system stopped.")

    @filter.command("perception_status")
    async def perception_status(self, event: AstrMessageEvent):
        """查看当前 Perception 系统状态。"""
        _ = event
        if not self.perception_enabled:
            yield event.plain_result("Perception: disabled")
            return

        status = self.perception.get_system_status()
        last_signal = self._recent_signals[-1]["summary"] if self._recent_signals else "None"
        text = (
            "Perception System Status\n\n"
            f"System: {'running' if status['running'] else 'stopped'}\n"
            f"Collectors: {status['collectors_count']}\n"
            f"Event Queue: {status['event_queue_size']}\n"
            f"Signal Queue: {status['signal_queue_size']}\n"
            f"Recent Signals(cache): {len(self._recent_signals)}\n"
            f"Last Signal: {last_signal}"
        )
        yield event.plain_result(text)

    async def _signal_loop(self) -> None:
        """持续监听 Reflex 输出信号并执行通知。"""
        while True:
            try:
                signal = await self.perception.get_signal()
                await self._handle_signal(signal)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"signal loop error: {exc}")
                await asyncio.sleep(1.0)

    async def _handle_signal(self, signal: ReflexSignal) -> None:
        """处理单条 Reflex 信号。"""
        self._append_signal_cache(signal)
        self._append_event_cache(signal)

        prompt = self._build_signal_prompt(signal)
        try:
            llm_resp = await self._call_llm(prompt)
            text = self._extract_completion_text(llm_resp).strip()
        except Exception as exc:
            logger.error(f"signal llm call failed: {exc}")
            return

        if not text:
            return

        try:
            await self._send_notification(text)
        except Exception as exc:
            logger.error(f"signal notify failed: {exc}")

    def _build_signal_prompt(self, signal: ReflexSignal) -> str:
        """构建对用户通知的自然语言提示。"""
        return (
            "You are an AI assistant that can sense its own system status.\n\n"
            "Recently you detected the following internal signals:\n\n"
            f"Summary: {signal.summary}\n"
            f"Reason: {signal.reason}\n"
            f"Events Count: {len(signal.events)}\n\n"
            "Describe the issue naturally as if you feel something is wrong.\n"
            "Explain what might be happening.\n"
            "Respond in a short message to the user."
        )

    async def _llm_generate_for_reflex(self, prompt: str) -> str:
        """提供给 Perception ReflexEngine 的 LLM 生成函数。"""
        resp = await self._call_llm(prompt)
        return self._extract_completion_text(resp)

    async def _call_llm(self, prompt: str) -> Any:
        """调用 AstrBot LLM 接口。"""
        if self._default_provider_id:
            return await self.context.llm_generate(
                chat_provider_id=self._default_provider_id,
                prompt=prompt,
            )
        return await self.context.llm_generate(prompt=prompt)

    def _extract_completion_text(self, response: Any) -> str:
        """从 LLM 返回对象中提取文本。"""
        if isinstance(response, str):
            return response
        text = getattr(response, "completion_text", "")
        if text:
            return str(text)
        return str(response)

    async def _send_notification(self, text: str) -> None:
        """发送主动通知消息。优先使用 unified_msg_origin。"""
        if self._notify_unified_msg_origin:
            chain = MessageChain().message(text)
            await self.context.send_message(self._notify_unified_msg_origin, chain)
            return

        if self._notify_user_id:
            # 兼容部分版本/适配器可能提供的 user_id 形式发送接口。
            await self.context.send_message(user_id=self._notify_user_id, content=text)
            return

        logger.warning("No notify target configured (notify_unified_msg_origin / notify_user_id).")

    def _append_signal_cache(self, signal: ReflexSignal) -> None:
        """缓存近期信号摘要。"""
        self._recent_signals.append(
            {
                "timestamp": datetime.now().isoformat(),
                "summary": signal.summary,
                "reason": signal.reason,
                "events_count": len(signal.events),
            }
        )

    def _append_event_cache(self, signal: ReflexSignal) -> None:
        """从信号内携带事件缓存近期事件快照。"""
        now = datetime.now().isoformat()
        for event in signal.events:
            self._recent_events.append(
                {
                    "timestamp": now,
                    "type": event.type,
                    "level": event.level.value,
                    "message": event.message,
                    "context": event.context,
                }
            )

    def _get_recent_signals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取近期信号。"""
        if limit <= 0:
            return []
        return list(self._recent_signals)[-limit:]

    def _get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取近期事件快照。"""
        if limit <= 0:
            return []
        return list(self._recent_events)[-limit:]

    def _build_perception_config(self) -> Dict[str, Any]:
        """从插件配置映射 PerceptionManager 配置。"""
        mapping = {
            "stream_window_seconds": self.config.get("stream_window_seconds"),
            "collector_tick_interval": self.config.get("collector_tick_interval"),
            "trend_interval_seconds": self.config.get("trend_interval_seconds"),
            "collector_default_interval_seconds": self.config.get("collector_default_interval_seconds"),
            "collector_rate_limit": self.config.get("collector_rate_limit"),
            "collector_no_data_threshold": self.config.get("collector_no_data_threshold"),
            "collector_timeout_seconds": self.config.get("collector_timeout_seconds"),
            "collector_offline_factor": self.config.get("collector_offline_factor"),
            "event_queue_size": self.config.get("event_queue_size"),
            "reflex_batch_size": self.config.get("reflex_batch_size"),
            "reflex_batch_timeout": self.config.get("reflex_batch_timeout"),
            "reflex_rate_limit": self.config.get("reflex_rate_limit"),
        }
        return {k: v for k, v in mapping.items() if v is not None}

    def _register_tools(self) -> None:
        """注册 LLM Tool（兼容新旧 AstrBot 版本）。"""
        tools = [
            GetSystemStatusTool(getter=self.perception.get_system_status),
            GetCurrentSystemInfoTool(getter=self.perception.get_current_system_info),
            GetRecentSignalsTool(getter=self._get_recent_signals),
            GetRecentEventsTool(getter=self._get_recent_events),
        ]

        if hasattr(self.context, "add_llm_tools"):
            self.context.add_llm_tools(*tools)
            return

        tool_mgr = self.context.provider_manager.llm_tools
        for tool in tools:
            tool_mgr.func_list.append(tool)
