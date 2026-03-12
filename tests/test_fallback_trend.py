import asyncio
import sys
from datetime import datetime, timedelta
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
from perception.models import Observation, SourceType, TrendDirection
from perception.stream import ObservationStream
from perception.trend import BaseTrendStrategy, FallbackMetricTrendStrategy, TrendEngine


class BrokenStrategy(BaseTrendStrategy):
    def __init__(self):
        super().__init__(
            metric="memory.percent",
            window=timedelta(seconds=30),
            interval=timedelta(seconds=30),
            name="BrokenStrategy",
        )

    def compute_trends(self, observations):
        _ = observations
        raise RuntimeError("boom")


def _obs(metric, value, source, timestamp, tags=None):
    return Observation(
        id=f"{metric}-{timestamp.timestamp()}-{value}",
        source=source,
        metric=metric,
        value=value,
        timestamp=timestamp,
        tags=tags or {},
    )


def test_fallback_trend_groups_series_by_metric_and_tags():
    strategy = FallbackMetricTrendStrategy(window=timedelta(seconds=30), interval=timedelta(seconds=30))
    now = datetime.now()
    observations = [
        _obs("process.top.memory_percent", 10.0, SourceType.PROCESS, now - timedelta(seconds=20), {"pid": 1, "rank": 1}),
        _obs("process.top.memory_percent", 20.0, SourceType.PROCESS, now - timedelta(seconds=10), {"pid": 1, "rank": 1}),
        _obs("process.top.memory_percent", 30.0, SourceType.PROCESS, now, {"pid": 1, "rank": 1}),
        _obs("process.top.memory_percent", 5.0, SourceType.PROCESS, now - timedelta(seconds=20), {"pid": 2, "rank": 2}),
        _obs("process.top.memory_percent", 6.0, SourceType.PROCESS, now - timedelta(seconds=10), {"pid": 2, "rank": 2}),
        _obs("process.top.memory_percent", 7.0, SourceType.PROCESS, now, {"pid": 2, "rank": 2}),
    ]

    trends = strategy.compute_trends(observations)

    assert len(trends) == 2
    assert {trend.metric for trend in trends} == {"process.top.memory_percent"}
    assert len({trend.series_key for trend in trends}) == 2
    assert all(trend.samples == 3 for trend in trends)
    assert {trend.series_tags["pid"] for trend in trends} == {1, 2}


def test_fallback_trend_requires_minimum_samples():
    strategy = FallbackMetricTrendStrategy(window=timedelta(seconds=30), interval=timedelta(seconds=30))
    now = datetime.now()
    trends = strategy.compute_trends(
        [
            _obs("cpu.percent", 10.0, SourceType.CPU, now - timedelta(seconds=5)),
            _obs("cpu.percent", 20.0, SourceType.CPU, now),
        ]
    )

    assert trends == []


def test_trend_engine_uses_fallback_and_respects_explicit_coverage():
    stream = ObservationStream(time_window=timedelta(seconds=60))
    event_manager = EventManager()
    engine = TrendEngine(
        stream=stream,
        event_manager=event_manager,
        fallback_window=timedelta(seconds=30),
        fallback_interval=timedelta(seconds=30),
        max_trends=10,
    )
    engine.register_strategy(
        FallbackMetricTrendStrategy(
            metric="memory.percent",
            window=timedelta(seconds=30),
            interval=timedelta(seconds=30),
            name="ExplicitMemoryStrategy",
        )
    )

    now = datetime.now()
    stream.push_many(
        [
            _obs("memory.percent", 10.0, SourceType.MEMORY, now - timedelta(seconds=20)),
            _obs("memory.percent", 20.0, SourceType.MEMORY, now - timedelta(seconds=10)),
            _obs("memory.percent", 30.0, SourceType.MEMORY, now),
            _obs("cpu.percent", 20.0, SourceType.CPU, now - timedelta(seconds=20)),
            _obs("cpu.percent", 30.0, SourceType.CPU, now - timedelta(seconds=10)),
            _obs("cpu.percent", 40.0, SourceType.CPU, now),
        ]
    )

    trends = asyncio.run(engine.analyze())

    assert len([trend for trend in trends if trend.metric == "memory.percent"]) == 1
    assert len([trend for trend in trends if trend.metric == "cpu.percent"]) == 1
    assert event_manager.queue().qsize() == 0
    assert engine.fallback_strategy.window.total_seconds() == 30
    assert engine.fallback_strategy.interval.total_seconds() == 30


def test_trend_engine_emits_strategy_error_and_keeps_fallback_running():
    stream = ObservationStream(time_window=timedelta(seconds=60))
    event_manager = EventManager()
    engine = TrendEngine(
        stream=stream,
        event_manager=event_manager,
        fallback_window=timedelta(seconds=30),
        fallback_interval=timedelta(seconds=30),
    )
    engine.register_strategy(BrokenStrategy())

    now = datetime.now()
    stream.push_many(
        [
            _obs("memory.percent", 10.0, SourceType.MEMORY, now - timedelta(seconds=20)),
            _obs("memory.percent", 20.0, SourceType.MEMORY, now - timedelta(seconds=10)),
            _obs("memory.percent", 30.0, SourceType.MEMORY, now),
            _obs("cpu.percent", 10.0, SourceType.CPU, now - timedelta(seconds=20)),
            _obs("cpu.percent", 20.0, SourceType.CPU, now - timedelta(seconds=10)),
            _obs("cpu.percent", 30.0, SourceType.CPU, now),
        ]
    )

    trends = asyncio.run(engine.analyze())

    assert any(trend.metric == "cpu.percent" for trend in trends)
    assert all(trend.metric != "memory.percent" for trend in trends)
    event = event_manager.queue().get_nowait()
    assert event.type == "TrendStrategyErrorEvent"
    assert event.context["strategy_name"] == "BrokenStrategy"
