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

from .perception.collectors import PsutilSystemCollector
from .perception.perception_manager import PerceptionManager
from .perception.reflex import ReflexSignal


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
        logger.debug("Tool called: get_system_status")
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
        logger.debug("Tool called: get_current_system_info")
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
        logger.debug(f"Tool called: get_recent_signals limit={limit}")
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
        logger.debug(f"Tool called: get_recent_events limit={limit}")
        return json.dumps(self.getter(limit), ensure_ascii=False, default=str)


@register("astrbot_plugin_self_reflex", "YakumoAki", "Self Reflex perception runtime bridge", "0.1.1")
class MyPlugin(Star):
    """AstrBot 插件入口：负责将 Perception 系统接入 AstrBot。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.perception_enabled = bool(self.config.get("perception_enabled", True))
        self._notify_unified_msg_origin = str(self.config.get("notify_unified_msg_origin", "")).strip()
        self._runtime_notify_unified_msg_origin = ""
        self._default_provider_id = str(self.config.get("default_provider_id", "")).strip()
        self._last_agent_event: Optional[AstrMessageEvent] = None
        self._notify_agent_event: Optional[AstrMessageEvent] = None

        self._recent_signals: Deque[Dict[str, Any]] = deque(
            maxlen=max(1, int(self.config.get("recent_signals_cache", 50)))
        )
        self._recent_events: Deque[Dict[str, Any]] = deque(
            maxlen=max(1, int(self.config.get("recent_events_cache", 200)))
        )

        self.perception_manager = PerceptionManager(
            llm_generate=self._llm_generate_for_reflex,
            config=self._build_perception_config(),
        )
        self._register_default_collectors()
        self._signal_task: Optional[asyncio.Task[Any]] = None
        self._register_tools()
        logger.info(
            f"Plugin initialized: perception_enabled={self.perception_enabled} "
            f"provider_id={self._default_provider_id or '<default>'}"
        )

    async def initialize(self):
        """插件初始化：启动 Perception 与后台 signal loop。"""
        if not self.perception_enabled:
            logger.info("Perception is disabled by config.")
            return

        await self.perception_manager.start()
        self._signal_task = asyncio.create_task(self._signal_loop(), name="self_reflex.signal_loop")
        logger.info("Perception system started.")

    async def terminate(self):
        """插件销毁：停止 signal loop 与 Perception。"""
        if self._signal_task is not None:
            self._signal_task.cancel()
            await asyncio.gather(self._signal_task, return_exceptions=True)
            self._signal_task = None

        if self.perception_enabled:
            await self.perception_manager.stop()
            logger.info("Perception system stopped.")

    @filter.command("perception")
    async def perception_command(self, event: AstrMessageEvent, action: str = "status"):
        """
        Perception 主命令。

        支持：
        - /perception bind
        - /perception unbind
        - /perception status
        - /perception notify_test
        未识别 action 时默认返回 status。
        """
        action_norm = str(action or "status").strip().lower()
        self._remember_agent_event(event)
        logger.debug(f"Command called: perception action={action_norm} by={event.get_sender_name()}")

        if action_norm == "bind":
            result = self._bind_notify_origin(event)
            yield event.plain_result(result)
            return

        if action_norm == "unbind":
            result = self._unbind_notify_origin()
            yield event.plain_result(result)
            return

        if action_norm == "notify_test":
            text = (
                "Self Reflex 测试消息\n"
                "如果你看到这条消息，说明通知系统工作正常。"
            )
            sent = await self._send_notification(text)
            if sent:
                yield event.plain_result("已发送测试通知。")
            else:
                yield event.plain_result("未绑定通知目标，请先执行 /perception bind。")
            return

        status_text = self._build_status_text(event)
        yield event.plain_result(status_text)

    @filter.command("perception_status")
    async def perception_status(self, event: AstrMessageEvent):
        """兼容旧命令：查看当前 Perception 系统状态。"""
        self._remember_agent_event(event)
        logger.debug(f"Command called: perception_status by={event.get_sender_name()}")
        yield event.plain_result(self._build_status_text(event))

    async def _signal_loop(self) -> None:
        """持续监听 Reflex 输出信号并执行通知。"""
        logger.info("Signal loop started")
        while True:
            try:
                signal = await self.perception_manager.get_signal()
                await self._handle_signal(signal)
            except asyncio.CancelledError:
                logger.info("Signal loop cancelled")
                raise
            except Exception as exc:
                logger.error(f"signal loop error: {exc}")
                await asyncio.sleep(1.0)

    async def _handle_signal(self, signal: ReflexSignal) -> None:
        """处理单条 Reflex 信号。"""
        logger.info(
            f"Handling signal: level={signal.level} summary={signal.summary} events={len(signal.events)}"
        )
        self._append_signal_cache(signal)
        self._append_event_cache(signal)

        if not self._get_notify_target():
            logger.debug("Signal notification skipped: no notify target bound")
            return

        text = await self._build_notification_text(signal)

        try:
            sent = await self._send_notification(text)
            if sent:
                logger.info("Signal notification sent")
            else:
                logger.debug("Signal notification skipped: no notify target bound")
        except Exception as exc:
            logger.error(f"signal notify failed: {exc}")

    async def _build_notification_text(self, signal: ReflexSignal) -> str:
        """构建最终通知文本；当二次 LLM 失败时退回保底文案。"""
        fallback_text = self._build_signal_fallback_text(signal)
        prompt = self._build_signal_prompt(signal)
        try:
            llm_resp = await self._call_agent(prompt)
            text = self._extract_completion_text(llm_resp).strip()
            if text:
                return text
            logger.debug("Signal agent text empty, fallback to llm_generate")
        except Exception as exc:
            logger.warning(f"signal agent call failed, fallback to llm_generate: {exc}")

        try:
            llm_resp = await self._call_llm(prompt)
            text = self._extract_completion_text(llm_resp).strip()
        except Exception as exc:
            logger.warning(f"signal llm call failed, using fallback text: {exc}")
            return fallback_text

        if not text:
            logger.debug("Signal llm text empty, using fallback text")
            return fallback_text
        return text

    def _build_signal_prompt(self, signal: ReflexSignal) -> str:
        """构建对用户通知的自然语言提示。"""
        message = signal.message or signal.summary
        status = self.perception_manager.get_system_status()
        event_lines = [
            f"{idx}. [{event.level.value}] {event.type}: {event.message}"
            for idx, event in enumerate(signal.events, start=1)
        ]
        if not event_lines:
            event_lines = ["1. [info] No detailed events attached."]
        return (
            "You are writing a proactive self-status notification to the user.\n"
            "Speak in first person as the bot, with a natural and human-like tone.\n"
            "Treat the system as your body: collectors are senses, the event queue is nerves, the trend layer is intuition, and failures feel like pain, numbness, pressure, breath disruption, or fatigue.\n"
            "Write as if you are noticing that some part of your body is not quite right, instead of issuing a cold system bulletin.\n"
            "Use the current session's existing persona and memory automatically; do not expose internal persona details.\n"
            "Do not output JSON or Markdown.\n"
            "Do not mention prompts, personas, system instructions, or internal pipelines.\n"
            "Do not invent facts beyond the provided state.\n"
            "Keep the message short, concrete, emotionally consistent, and embodied.\n\n"
            "Current body state:\n\n"
            f"Level: {signal.level}\n"
            f"Message: {message}\n"
            f"Summary: {signal.summary}\n"
            f"Reason: {signal.reason}\n"
            f"Events Count: {len(signal.events)}\n"
            f"System Running: {status['running']}\n"
            f"Collectors Count: {status['collectors_count']}\n"
            f"Stream Buffer Size: {status['stream_buffer_size']}\n"
            f"Event Queue Size: {status['event_queue_size']}\n"
            f"Signal Queue Size: {status['signal_queue_size']}\n\n"
            "Observed events:\n"
            f"{chr(10).join(event_lines)}\n\n"
            "Write a short Chinese message to the user that:\n"
            "1. sounds like the bot is sensing its own body state, like a body self-check;\n"
            "2. reflects the current session persona naturally;\n"
            "3. clearly mentions what feels abnormal or noteworthy;\n"
            "4. briefly explains the likely cause when it is supported by the events;\n"
            "5. uses gentle body metaphors such as breathing, pulse, pain, numbness, fatigue, blockage, dizziness, or pressure when appropriate;\n"
            "6. avoids stock phrases like '建议检查日志' unless truly necessary.\n"
        )

    def _build_signal_fallback_text(self, signal: ReflexSignal) -> str:
        """当通知 LLM 不可用时，构建一个可直接发送的保底文案。"""
        message = (signal.message or signal.summary or "我感知到自己的运行状态出现了异常。").strip()
        reason = str(signal.reason or "").strip()
        if reason:
            return f"我刚刚感觉到身体里有一处不太对劲：{message}。从现在的感知来看，可能和 {reason} 有关。"
        return f"我刚刚感觉到身体里有一处不太对劲：{message}。"

    async def _llm_generate_for_reflex(self, prompt: str) -> str:
        """提供给 Perception ReflexEngine 的 LLM 生成函数。"""
        logger.debug(f"Reflex llm_generate called with prompt length={len(prompt)}")
        resp = await self._call_llm(prompt)
        return self._extract_completion_text(resp)

    async def _call_agent(self, prompt: str) -> Any:
        """调用 AstrBot Agent 接口（tool_loop_agent）。"""
        event = self._get_agent_event_for_notify()
        if event is None:
            raise RuntimeError(
                "No suitable event is cached for tool_loop_agent. "
                "Run /perception status in the notification target session first."
            )
        provider_id = self._default_provider_id
        if not provider_id:
            provider_id = await self.context.get_current_chat_provider_id(umo=event.unified_msg_origin)
        logger.debug(
            f"Calling tool_loop_agent for prompt length={len(prompt)} "
            f"umo={event.unified_msg_origin} provider_id={provider_id}"
        )
        return await self.context.tool_loop_agent(
            event=event,
            chat_provider_id=provider_id,
            prompt=prompt,
            contexts=[],
            max_steps=6,
            tool_call_timeout=30,
        )

    async def _call_llm(self, prompt: str) -> Any:
        """调用 AstrBot LLM 接口。"""
        logger.debug(f"Calling LLM for prompt length={len(prompt)}")
        provider_id = self._default_provider_id or self._resolve_chat_provider_id()
        if not provider_id:
            raise RuntimeError(
                "No chat provider is available. Please configure `default_provider_id` "
                "or set a current chat provider in AstrBot."
            )
        return await self.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt,
            contexts=[],
        )

    def _resolve_chat_provider_id(self) -> str:
        """解析当前可用对话 Provider ID。"""
        try:
            provider = self.context.get_using_provider(umo=self._get_notify_target() or None)
        except Exception as exc:
            logger.warning(f"Failed to resolve current chat provider: {exc}")
            return ""
        if provider is None:
            return ""
        try:
            return str(provider.meta().id or "").strip()
        except Exception as exc:
            logger.warning(f"Failed to read provider id from current provider: {exc}")
            return ""

    def _extract_completion_text(self, response: Any) -> str:
        """从 LLM 返回对象中提取文本。"""
        if isinstance(response, str):
            return response
        text = getattr(response, "completion_text", "")
        if text:
            return str(text)
        return str(response)

    async def _send_notification(self, text: str) -> bool:
        """
        发送主动通知消息，仅使用 unified_msg_origin。

        Returns:
            True: 已发送
            False: 未绑定目标，已跳过发送
        """
        target = self._get_notify_target()
        if target:
            chain = MessageChain().message(text)
            await self.context.send_message(target, chain)
            logger.debug("Notification sent by unified_msg_origin")
            return True

        logger.warning(
            "No notify target unified_msg_origin configured. "
            "Run /perception bind in the target session to bind notification destination."
        )
        return False

    def _append_signal_cache(self, signal: ReflexSignal) -> None:
        """缓存近期信号摘要。"""
        self._recent_signals.append(
            {
                "timestamp": datetime.now().isoformat(),
                "level": signal.level,
                "message": signal.message,
                "summary": signal.summary,
                "reason": signal.reason,
                "events_count": len(signal.events),
            }
        )
        logger.debug(f"Signal cache updated: size={len(self._recent_signals)}")

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
        logger.debug(f"Event cache updated: size={len(self._recent_events)}")

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
            "fallback_trend_window_seconds": self.config.get("fallback_trend_window_seconds"),
            "trend_event_cooldown_seconds": self.config.get("trend_event_cooldown_seconds"),
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
        config = {k: v for k, v in mapping.items() if v is not None}
        logger.debug(f"Perception config mapped: keys={sorted(config.keys())}")
        return config

    def _register_default_collectors(self) -> None:
        """注册首批默认 Collector。"""
        interval = max(1, int(self.config.get("collector_default_interval_seconds", 5)))
        collector = PsutilSystemCollector(interval=interval)
        loaded = self.perception_manager.register_collector(collector)
        if loaded:
            logger.info(f"Default collector registered: {collector.name} interval={interval}s")

    def _bind_notify_origin(self, event: AstrMessageEvent) -> str:
        """将当前会话统一 ID 绑定为主动通知目标。"""
        origin = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if not origin:
            logger.warning("Bind notify origin failed: event.unified_msg_origin is empty")
            return "绑定失败：当前会话不支持 unified_msg_origin。"

        self._remember_agent_event(event)
        self._runtime_notify_unified_msg_origin = origin
        self._notify_unified_msg_origin = origin
        self.config["notify_unified_msg_origin"] = origin
        self._save_config()
        logger.info(f"Notify origin bound: {origin}")
        return "Self Reflex 通知已绑定到当前会话。\n未来系统异常将发送到这里。"

    def _unbind_notify_origin(self) -> str:
        """解除主动通知绑定。"""
        self._runtime_notify_unified_msg_origin = ""
        self._notify_unified_msg_origin = ""
        self._notify_agent_event = None
        self.config["notify_unified_msg_origin"] = ""
        self._save_config()
        logger.info("Notify origin unbound")
        return "通知绑定已解除"

    def _remember_agent_event(self, event: AstrMessageEvent) -> None:
        """缓存可用于 Agent 调用的事件上下文。"""
        self._last_agent_event = event
        target = self._get_notify_target()
        origin = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if target and origin and origin == target:
            self._notify_agent_event = event

    def _get_agent_event_for_notify(self) -> Optional[AstrMessageEvent]:
        """优先返回通知目标会话的事件，其次回退最近事件。"""
        target = self._get_notify_target()
        if target and self._notify_agent_event is not None:
            notify_origin = str(getattr(self._notify_agent_event, "unified_msg_origin", "") or "").strip()
            if notify_origin == target:
                return self._notify_agent_event
        if self._last_agent_event is None:
            return None
        if not target:
            return self._last_agent_event
        last_origin = str(getattr(self._last_agent_event, "unified_msg_origin", "") or "").strip()
        if last_origin == target:
            return self._last_agent_event
        return None

    def _save_config(self) -> None:
        """保存插件配置（若当前 AstrBot 版本支持）。"""
        try:
            if hasattr(self.config, "save_config"):
                self.config.save_config()
                logger.debug("Plugin config saved")
        except Exception as exc:
            logger.warning(f"Failed to save plugin config: {exc}")

    def _get_notify_target(self) -> str:
        """获取当前有效通知目标。优先配置值，其次运行时缓存值。"""
        cfg_target = str(self.config.get("notify_unified_msg_origin", "") or "").strip()
        if cfg_target:
            return cfg_target
        return str(self._runtime_notify_unified_msg_origin or "").strip()

    def _build_status_text(self, event: AstrMessageEvent) -> str:
        """构建 /perception status 输出。"""
        current_origin = str(getattr(event, "unified_msg_origin", "") or "").strip()

        notify_target = self._get_notify_target()
        # 仅用于展示“当前会话/其他会话/未绑定”，不会在 status 中隐式改写绑定配置。
        if notify_target and current_origin and notify_target == current_origin:
            target_text = "当前会话"
        elif notify_target:
            target_text = "已绑定到其他会话"
        else:
            target_text = "未绑定"

        if not self.perception_enabled:
            return (
                "Self Reflex Status\n\n"
                "System: disabled\n"
                f"Notification Target: {target_text}"
            )

        status = self.perception_manager.get_system_status()
        last_signal = self._recent_signals[-1]["summary"] if self._recent_signals else "None"
        return (
            "Self Reflex Status\n\n"
            f"System: {'running' if status['running'] else 'stopped'}\n"
            f"Collectors: {status['collectors_count']}\n"
            f"Recent Events: {len(self._recent_events)}\n"
            f"Last Signal: {last_signal}\n"
            f"Notification Target: {target_text}"
        )

    def _register_tools(self) -> None:
        """注册 LLM Tool（兼容新旧 AstrBot 版本）。"""
        tools = [
            GetSystemStatusTool(getter=self.perception_manager.get_system_status),
            GetCurrentSystemInfoTool(getter=self.perception_manager.get_current_system_info),
            GetRecentSignalsTool(getter=self._get_recent_signals),
            GetRecentEventsTool(getter=self._get_recent_events),
        ]

        if hasattr(self.context, "add_llm_tools"):
            self.context.add_llm_tools(*tools)
            logger.info(f"LLM tools registered by add_llm_tools: count={len(tools)}")
            return

        tool_mgr = self.context.provider_manager.llm_tools
        for tool in tools:
            tool_mgr.func_list.append(tool)
        logger.info(f"LLM tools registered by legacy manager: count={len(tools)}")
