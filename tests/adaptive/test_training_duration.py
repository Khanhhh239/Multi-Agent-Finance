"""A long elapsed time must not terminate training; the RAM guard still applies."""

from types import SimpleNamespace
import pytest
from agent1_service.workspace import train_worker


def fake_worker(monkeypatch, memory=0):
    child = SimpleNamespace(
        pid=123,
        start=lambda: None,
        is_alive=lambda: True,
        join=lambda *a: None,
        terminate=lambda: None,
        close=lambda: None,
    )
    reader = SimpleNamespace(
        poll=lambda _: True, recv=lambda: ("ready", {}), close=lambda: None
    )
    writer = SimpleNamespace(close=lambda: None)
    context = SimpleNamespace(
        Pipe=lambda **kw: (reader, writer), Process=lambda **kw: child
    )
    monkeypatch.setattr(train_worker.mp, "get_context", lambda _: context)
    import psutil

    monkeypatch.setattr(
        psutil,
        "Process",
        lambda _: SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=memory)),
    )
    ticks = iter([0, 7200, 7201])
    monkeypatch.setattr(train_worker.time, "monotonic", lambda: next(ticks))


def test_two_hour_job_completes_even_with_old_timeout_env(monkeypatch):
    monkeypatch.setenv("AGENT1_TRAIN_SECONDS", "1")
    fake_worker(monkeypatch)
    messages = []
    result = train_worker.isolated_train({}, "2026-10-31", False, messages.append)
    assert result["training_seconds"] == 7201
    assert any("7200" in message for message in messages)


def test_memory_guard_remains_active(monkeypatch):
    monkeypatch.setenv("AGENT1_TRAIN_MIB", "128")
    fake_worker(monkeypatch, memory=129 * 2**20)
    with pytest.raises(ValueError, match="RAM"):
        train_worker.isolated_train({}, "2026-10-31", False, lambda _: None)
