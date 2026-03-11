"""Minimal tests for Reflex core pipeline."""

from __future__ import annotations

import unittest

from core.collectors.test_collector import RandomCPUCollector
from core.interfaces.collector import BaseCollector
from core.models.metric import CurrentMetric
from core.trend.detector import (
    detect_burst,
    detect_falling_fast,
    detect_rising_fast,
    detect_sustained_high,
)
from core.trend.engine import TrendEngine
from core.trend.window import MetricWindow


class MetricWindowTests(unittest.TestCase):
    def test_window_add_and_maxlen(self) -> None:
        window = MetricWindow()
        for i in range(12):
            window.add(timestamp=float(i), value=float(i))

        self.assertEqual(window.size(), 10)
        self.assertEqual(window.values()[0], 2.0)
        self.assertEqual(window.values()[-1], 11.0)
        self.assertEqual(window.timestamps()[0], 2.0)
        self.assertEqual(window.timestamps()[-1], 11.0)


class DetectorTests(unittest.TestCase):
    def test_detect_sustained_high(self) -> None:
        self.assertTrue(detect_sustained_high([60, 81, 85, 90]))
        self.assertFalse(detect_sustained_high([81, 79, 90]))
        self.assertFalse(detect_sustained_high([90, 91]))

    def test_detect_rising_fast(self) -> None:
        self.assertTrue(detect_rising_fast([10, 35], delta=20))
        self.assertFalse(detect_rising_fast([10, 25], delta=20))

    def test_detect_falling_fast(self) -> None:
        self.assertTrue(detect_falling_fast([80, 55], delta=20))
        self.assertFalse(detect_falling_fast([80, 65], delta=20))

    def test_detect_burst(self) -> None:
        self.assertTrue(detect_burst([40, 75], delta=30))
        self.assertFalse(detect_burst([40, 60], delta=30))


class TrendEngineTests(unittest.TestCase):
    def _metric(self, value: float, ts: float) -> CurrentMetric:
        return CurrentMetric(
            source="hardware",
            timestamp=ts,
            name="cpu_usage",
            value=value,
            tags={"core": "all"},
        )

    def test_process_detects_sustained_high(self) -> None:
        engine = TrendEngine()
        engine.process(self._metric(81.0, 1.0))
        engine.process(self._metric(82.0, 2.0))
        trends = engine.process(self._metric(83.0, 3.0))

        trend_types = {trend.trend_type for trend in trends}
        self.assertIn("sustained_high", trend_types)

    def test_process_detects_rising_and_burst(self) -> None:
        engine = TrendEngine()
        engine.process(self._metric(10.0, 1.0))
        trends = engine.process(self._metric(45.0, 2.0))

        trend_types = {trend.trend_type for trend in trends}
        self.assertIn("rising_fast", trend_types)
        self.assertIn("burst", trend_types)


class RandomCollectorTests(unittest.TestCase):
    def test_collector_matches_base_interface(self) -> None:
        collector = RandomCPUCollector()
        self.assertIsInstance(collector, BaseCollector)

    def test_collect_returns_current_metric(self) -> None:
        collector = RandomCPUCollector()
        records = collector.collect()

        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], CurrentMetric)
        self.assertEqual(records[0].name, "cpu_usage")
        self.assertGreaterEqual(records[0].value, 0.0)
        self.assertLessEqual(records[0].value, 100.0)


if __name__ == "__main__":
    unittest.main()

