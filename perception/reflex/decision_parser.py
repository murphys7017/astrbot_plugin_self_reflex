"""Reflex 决策解析器。"""

import json
from dataclasses import dataclass
from typing import List

from astrbot.api import logger
from ..models import Event


@dataclass
class ReflexSignal:
    """Reflex 输出信号。"""

    push: bool  # 是否需要上报到用户
    summary: str  # 信号摘要（用于状态面板/日志）
    message: str  # 信号短消息（用于通知 prompt）
    reason: str  # 触发或过滤原因
    level: str  # 信号级别：info/warning/critical
    events: List[Event]  # 参与决策的原始事件批次


class DecisionParser:
    """将 LLM 输出解析为 ReflexSignal。"""

    def parse(self, llm_text: str, events: List[Event]) -> ReflexSignal:
        """
        解析 LLM 输出 JSON。

        要求模型返回字段：
        - push
        - level
        - message
        - summary
        - reason

        解析失败时返回 push=False，并尽量推断 level。
        """
        json_text = self._extract_json(llm_text)
        if json_text is None:
            logger.debug("DecisionParser parse failed: no json object found")
            return ReflexSignal(
                push=False,
                summary="",
                message="",
                reason="invalid_json",
                level=self._infer_level(events),
                events=events,
            )

        try:
            payload = json.loads(json_text)
        except (json.JSONDecodeError, TypeError):
            logger.debug("DecisionParser parse failed: invalid json payload")
            return ReflexSignal(
                push=False,
                summary="",
                message="",
                reason="invalid_json",
                level=self._infer_level(events),
                events=events,
            )

        push_value = payload.get("push", False)
        if isinstance(push_value, bool):
            push = push_value
        elif isinstance(push_value, str):
            push = push_value.strip().lower() == "true"
        else:
            push = bool(push_value)

        summary = str(payload.get("summary", ""))
        message = str(payload.get("message", summary))
        reason = str(payload.get("reason", ""))
        level = self._normalize_level(payload.get("level"), default=self._infer_level(events))
        logger.debug(f"DecisionParser parsed signal: push={push} level={level} summary={summary}")
        return ReflexSignal(
            push=push,
            summary=summary,
            message=message,
            reason=reason,
            level=level,
            events=events,
        )

    def _infer_level(self, events: List[Event]) -> str:
        """根据事件列表推断信号级别。"""
        if not events:
            return "info"

        order = {"info": 1, "warning": 2, "critical": 3}
        highest = "info"
        for event in events:
            level = self._normalize_level(getattr(event.level, "value", event.level), default="info")
            if order.get(level, 0) > order.get(highest, 0):
                highest = level
        return highest

    def _normalize_level(self, value: object, default: str) -> str:
        """将任意输入规范化为 info/warning/critical。"""
        if value is None:
            return default

        level = str(value).strip().lower()
        if level in {"info", "warning", "critical"}:
            return level
        return default

    def _extract_json(self, text: str) -> str | None:
        """从文本中提取 JSON 对象字符串。"""
        if not text:
            return None

        raw = text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            candidates = [part.strip() for part in parts if part.strip()]
            for candidate in candidates:
                if candidate.startswith("{") and candidate.endswith("}"):
                    return candidate
                if "\n" in candidate:
                    tail = candidate.split("\n", 1)[1].strip()
                    if tail.startswith("{") and tail.endswith("}"):
                        return tail

        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        # 允许模型输出解释文本，提取最外层 JSON 片段用于解析。
        return raw[start : end + 1]
