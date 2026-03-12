import sys
from pathlib import Path
from types import SimpleNamespace

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perception.collectors.psutil_system import PsutilSystemCollector


class DummyProcess:
    def __init__(self, pid, name, status, memory_percent, cpu_percent, rss):
        self.info = {
            "pid": pid,
            "name": name,
            "status": status,
            "memory_percent": memory_percent,
        }
        self._cpu_percent = cpu_percent
        self._rss = rss

    def cpu_percent(self, interval=None):
        _ = interval
        return self._cpu_percent

    def memory_info(self):
        return SimpleNamespace(rss=self._rss)


class AccessDeniedProcess:
    info = {"pid": 999, "name": "blocked", "status": "sleeping", "memory_percent": 50.0}

    def cpu_percent(self, interval=None):
        _ = interval
        raise psutil.AccessDenied(pid=999)


def test_psutil_system_collector_collects_expected_metrics(monkeypatch):
    collector = PsutilSystemCollector(interval=5, top_processes=2)

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
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.process_iter",
        lambda attrs: iter(
            [
                DummyProcess(1, "alpha", "running", 10.0, 15.0, 1000),
                DummyProcess(2, "beta", "sleeping", 30.0, 5.0, 3000),
                DummyProcess(3, "gamma", "running", 20.0, 25.0, 2000),
            ]
        ),
    )

    observations = list(collector.collect())
    metrics = {obs.metric for obs in observations}

    assert "cpu.percent" in metrics
    assert "memory.percent" in metrics
    assert "disk.percent" in metrics
    assert "network.bytes_sent" in metrics
    assert "process.count" in metrics
    assert "process.top.memory_percent" in metrics
    assert "process.top.cpu_percent" in metrics
    assert "process.top.rss_bytes" in metrics

    top_memory = [obs for obs in observations if obs.metric == "process.top.memory_percent"]
    assert len(top_memory) == 2
    assert top_memory[0].tags["name"] == "beta"
    assert top_memory[0].tags["rank"] == 1
    assert top_memory[1].tags["name"] == "gamma"

    ids = {obs.id for obs in observations}
    timestamps = {obs.timestamp for obs in observations}
    assert len(ids) == len(observations)
    assert len(timestamps) == 1


def test_psutil_system_collector_skips_process_errors(monkeypatch):
    collector = PsutilSystemCollector(interval=5, top_processes=3)

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
    monkeypatch.setattr(
        "perception.collectors.psutil_system.psutil.process_iter",
        lambda attrs: iter(
            [
                DummyProcess(10, "ok", "running", 40.0, 2.0, 4096),
                AccessDeniedProcess(),
            ]
        ),
    )

    observations = list(collector.collect())
    top_process_names = [obs.tags.get("name") for obs in observations if obs.metric == "process.top.memory_percent"]

    assert top_process_names == ["ok"]
