import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

astrbot_module = ModuleType("astrbot")
astrbot_api_module = ModuleType("astrbot.api")
astrbot_api_module.logger = SimpleNamespace(
    debug=lambda *args, **kwargs: None,
    info=lambda *args, **kwargs: None,
    warning=lambda *args, **kwargs: None,
    error=lambda *args, **kwargs: None,
)
astrbot_module.api = astrbot_api_module
sys.modules.setdefault("astrbot", astrbot_module)
sys.modules.setdefault("astrbot.api", astrbot_api_module)

from perception.events import EventManager
from perception.models import Event, EventLevel
from perception.reflex import PromptBuilder, ReflexEngine


def test_prompt_builder_includes_system_state_snapshot():
    builder = PromptBuilder()
    prompt = builder.build(
        [
            Event(
                type="CollectorTimeoutEvent",
                level=EventLevel.WARNING,
                message="collector timeout",
                timestamp=None,
                context={"collector": "psutil_system"},
            )
        ],
        system_state={
            "runtime": {"running": True, "collectors_count": 1},
            "latest_metrics": {"cpu.percent": {"value": 42.0}},
        },
    )

    assert "Current system state snapshot:" in prompt
    assert "living body" in prompt
    assert "body condition" in prompt
    assert '"collectors_count": 1' in prompt
    assert '"cpu.percent"' in prompt
    assert "CollectorTimeoutEvent" in prompt


def test_reflex_engine_passes_system_state_to_prompt_builder():
    captured = {}

    async def fake_llm_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            {
                "push": False,
                "level": "info",
                "message": "",
                "summary": "",
                "reason": "test",
            }
        )

    async def scenario() -> None:
        event_manager = EventManager()
        engine = ReflexEngine(
            event_manager=event_manager,
            llm_generate=fake_llm_generate,
            system_state_getter=lambda: {
                "runtime": {"running": True},
                "latest_metrics": {"memory.percent": {"value": 65.0}},
            },
            batch_size=1,
            batch_timeout=0.1,
            rate_limit=0.0,
        )

        original_build = engine.prompt_builder.build

        def capture_build(events, system_state=None):
            captured["system_state"] = system_state
            return original_build(events, system_state=system_state)

        engine.prompt_builder.build = capture_build

        task = asyncio.create_task(engine.run())
        await event_manager.submit_event(
            Event(
                type="TrendDetectedEvent",
                level=EventLevel.WARNING,
                message="cpu rising",
                timestamp=None,
                context={"metric": "cpu.percent"},
            )
        )
        await asyncio.sleep(0.2)
        engine.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())

    assert captured["system_state"]["runtime"]["running"] is True
    assert captured["system_state"]["latest_metrics"]["memory.percent"]["value"] == 65.0
    assert "Current system state snapshot:" in captured["prompt"]
