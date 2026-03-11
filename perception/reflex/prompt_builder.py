"""Reflex Prompt 构建器。"""

from typing import List

from perception.models import Event


class PromptBuilder:
    """将事件批次转换为 LLM 输入 Prompt。"""

    def build(self, events: List[Event]) -> str:
        """构建用于事件升级判断的 Prompt。"""
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
                '  "summary": "...",',
                '  "reason": "..."',
                "}",
            ]
        )
        return "\n".join(lines)
