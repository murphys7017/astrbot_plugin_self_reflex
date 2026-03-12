import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perception.collectors.psutil_system import PsutilSystemCollector


def test_psutil_system_collector_collects_expected_metrics(monkeypatch):
    collector = PsutilSystemCollector(interval=5)

    monkeypatch.setattr("perception.collectors.psutil_system.os.getcwd", lambda: "C:\\workspace")
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.virtual_memory",
        lambda: SimpleNamespace(percent=72.5, used=1024, available=2048),
    )
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.swap_memory",
        lambda: SimpleNamespace(percent=12.5, used=512),
    )
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.disk_usage",
        lambda path: SimpleNamespace(percent=66.6, used=4096, free=8192),
    )
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.net_io_counters",
        lambda: SimpleNamespace(bytes_sent=111, bytes_recv=222),
    )
    monkeypatch.setattr("perception.collectors.psutil_system.psutil.pids", lambda: [1, 2, 3, 4])
    monkeypatch.setattr("perception.collectors.psutil_system.psutil.cpu_percent", lambda interval=None: 35.0)
    observations = list(collector.collect())
    metrics = {obs.metric for obs in observations}

    assert "cpu.percent" in metrics
    assert "memory.percent" in metrics
    assert "disk.percent" in metrics
    assert "network.bytes_sent" in metrics
    assert "process.count" in metrics
    assert all(not metric.startswith("process.top.") for metric in metrics)

    ids = {obs.id for obs in observations}
    timestamps = {obs.timestamp for obs in observations}
    assert len(ids) == len(observations)
    assert len(timestamps) == 1


def test_psutil_system_collector_returns_only_host_overview_metrics(monkeypatch):
    collector = PsutilSystemCollector(interval=5)

    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.virtual_memory",
        lambda: SimpleNamespace(percent=50.0, used=100, available=200),
    )
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.swap_memory",
        lambda: SimpleNamespace(percent=0.0, used=0),
    )
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.disk_usage",
        lambda path: SimpleNamespace(percent=10.0, used=1, free=9),
    )
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.net_io_counters",
        lambda: SimpleNamespace(bytes_sent=1, bytes_recv=2),
    )
    monkeypatch.setattr("perception.collectors.psutil_system.psutil.pids", lambda: [1, 2])
    monkeypatch.setattr("perception.collectors.psutil_system.psutil.cpu_percent", lambda interval=None: 1.0)
    observations = list(collector.collect())
    metric_to_tags = {obs.metric: obs.tags for obs in observations}

    assert set(metric_to_tags) == {
        "cpu.percent",
        "memory.percent",
        "memory.used_bytes",
        "memory.available_bytes",
        "swap.percent",
        "swap.used_bytes",
        "disk.percent",
        "disk.used_bytes",
        "disk.free_bytes",
        "network.bytes_sent",
        "network.bytes_recv",
        "process.count",
    }
    assert all(tags == {} for tags in metric_to_tags.values())
