"""Reflex 决策解析器。"""

import json
from dataclasses import dataclass
from typing import List

from perception.models import Event


@dataclass
class ReflexSignal:
    """Reflex 输出信号。"""

    push: bool
    summary: str
    reason: str
    events: List[Event]


class DecisionParser:
    """将 LLM 输出解析为 ReflexSignal。"""

    def parse(self, llm_text: str, events: List[Event]) -> ReflexSignal:
        """
        解析 LLM 输出 JSON。

        解析失败时返回 push=False。
        """
        json_text = self._extract_json(llm_text)
        if json_text is None:
            return ReflexSignal(push=False, summary="", reason="invalid_json", events=events)

        try:
            payload = json.loads(json_text)
        except (json.JSONDecodeError, TypeError):
            return ReflexSignal(push=False, summary="", reason="invalid_json", events=events)

        push_value = payload.get("push", False)
        if isinstance(push_value, bool):
            push = push_value
        elif isinstance(push_value, str):
            push = push_value.strip().lower() == "true"
        else:
            push = bool(push_value)

        summary = str(payload.get("summary", ""))
        reason = str(payload.get("reason", ""))
        return ReflexSignal(push=push, summary=summary, reason=reason, events=events)

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
        return raw[start : end + 1]
