"""Reflex 最小运行管线示例。"""

from __future__ import annotations

import time

from core.collectors.test_collector import RandomCPUCollector
from core.trend.engine import TrendEngine


def run_demo() -> None:
    """运行 Collector -> TrendEngine 的最小链路。"""
    collector = RandomCPUCollector()
    engine = TrendEngine()

    collector.start()
    try:
        while True:
            metrics = collector.collect()
            for metric in metrics:
                trends = engine.process(metric)
                print(f"metric {metric.name}={metric.value:g}")
                for trend in trends:
                    print(f"trend {trend.trend_type}")
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        collector.stop()


if __name__ == "__main__":
    run_demo()
