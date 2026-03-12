"""Reflex Prompt 构建器。"""

from typing import List

from astrbot.api import logger
from ..models import Event


class PromptBuilder:
    """将事件批次转换为 LLM 输入 Prompt。"""

    def build(self, events: List[Event]) -> str:
        """构建用于事件升级判断的 Prompt，要求模型返回结构化 JSON。"""
        # Prompt 保持结构化，便于模型稳定输出 JSON。
        lines = [
            "You are a system perception filter.",
            "",
            "Determine whether the following system events should be escalated.",
            "",
            "Events:",
            "",
        ]

        for idx, event in enumerate(events, start=1):
            level = event.level.value.upper()
            lines.append(f"{idx}. [{level}] {event.type} - {event.message}")

        lines.extend(
            [
                "",
                "Return JSON only:",
                '{',
                '  "push": true/false,',
                '  "level": "info|warning|critical",',
                '  "message": "...",',
                '  "summary": "...",',
                '  "reason": "..."',
                "}",
            ]
        )
        logger.debug(f"Reflex prompt built in PromptBuilder: events={len(events)}")
        return "\n".join(lines)
