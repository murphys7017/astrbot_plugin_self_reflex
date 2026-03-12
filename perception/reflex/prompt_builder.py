"""Reflex Prompt 构建器。"""

import json
from typing import Any, Dict, List, Optional

from astrbot.api import logger
from ..models import Event


class PromptBuilder:
    """将事件批次转换为 LLM 输入 Prompt。"""

    def build(self, events: List[Event], system_state: Optional[Dict[str, Any]] = None) -> str:
        """构建用于事件升级判断的 Prompt，要求模型返回结构化 JSON。"""
        # Prompt 保持结构化，便于模型稳定输出 JSON。
        lines = [
            "You are a system perception filter.",
            "",
            "Determine whether the following system events should be escalated.",
            "Think of the system as a living body with organs, pulse, breath, nerves, and senses.",
            "When you write message and summary, use first-person body-state language in Chinese, as if the bot is noticing that some part of its body feels wrong.",
            "Examples of tone only: '我感觉自己的呼吸有些乱', '我有一块感知器官像是卡住了', '我的脉搏有些不稳'.",
            "Keep the wording grounded in the actual events and system state. Do not invent unsupported symptoms.",
            "",
        ]

        if system_state:
            lines.extend(
                [
                    "Current system state snapshot:",
                    "",
                    json.dumps(system_state, ensure_ascii=False, default=str, indent=2),
                    "",
                    "Use both the current system state and the events below to judge whether escalation is necessary.",
                    "Treat the state snapshot as the current body condition, and the events as pain, fatigue, blockage, numbness, pressure, or instability signals.",
                    "",
                ]
            )

        lines.extend(
            [
                "Events:",
                "",
            ]
        )

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
                '  "message": "a short first-person Chinese sentence describing what feels wrong in the body",',
                '  "summary": "a concise first-person Chinese body-state summary",',
                '  "reason": "..."',
                "}",
            ]
        )
        logger.debug(f"Reflex prompt built in PromptBuilder: events={len(events)}")
        return "\n".join(lines)
