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
            "This is an AI self-status system, not a dramatic roleplay system.",
            "Use natural Chinese that sounds like a calm self-status broadcast from the bot.",
            "The style should be about 30% persona and 70% technical description.",
            "When you write message and summary, prefer a structure like: status category -> current state -> user impact.",
            "Available status categories include: compute state, memory state, inference state, network state, system state.",
            "Good examples of tone: '我这边 CPU 正在高负载运行，回复可能会稍微慢一点。', '当前系统压力较大，不过整体仍然稳定。', '我正在分析这个问题，可能需要一点时间。'",
            "Bad examples: 'CPU 呼吸困难', '系统窒息', '我的脉搏不稳'.",
            "Keep the wording grounded in the actual events and system state. Do not invent unsupported symptoms or causes.",
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
                    "Treat the state snapshot as real runtime evidence, and the events as status changes that may or may not deserve user-facing broadcast.",
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
                '  "message": "a short natural Chinese self-status broadcast from the bot",',
                '  "summary": "a concise Chinese self-status summary",',
                '  "reason": "..."',
                "}",
            ]
        )
        logger.debug(f"Reflex prompt built in PromptBuilder: events={len(events)}")
        return "\n".join(lines)
