import numpy as np
import cloudpickle
import pytest
import SciQLop.components.plotting.backend.remote.worker_handle as worker_handle_module
from SciQLop.components.plotting.backend.remote.worker_handle import RemoteWorker


class CollectingPipeline:
    def __init__(self):
        self.results = []
    def set_data(self, *views):
        self.results.append([np.array(v) for v in views])


def _sin_source(start, stop):
    x = np.linspace(start, stop, 16)
    return (x, np.sin(x))


def test_end_to_end_request_delivers_data(qtbot):
    worker = RemoteWorker(plugin_key="test_plugin")
    worker.start()
    try:
        pipe = CollectingPipeline()
        from SciQLop.components.plotting.backend.remote.channel import RemoteChannel
        ch = RemoteChannel(pipeline=pipe, channel_id=1, transport=worker)
        worker.register_channel(ch)
        worker.install(1, cloudpickle.dumps(_sin_source), arity=2)
        ch.on_data_requested_values(0.0, 6.28)
        qtbot.waitUntil(lambda: len(pipe.results) == 1, timeout=15000)
        x, y = pipe.results[0]
        assert x.shape == (16,)
        np.testing.assert_allclose(y, np.sin(x), atol=1e-6)
    finally:
        worker.shutdown()


def test_health_counters_emitted_around_request_response_cycle(qtbot, monkeypatch):
    calls = []
    monkeypatch.setattr(
        worker_handle_module.tracing, "counter",
        lambda name, value, cat=None: calls.append((name, value, cat)),
    )
    worker = RemoteWorker(plugin_key="test_plugin_counters")
    worker.start()
    try:
        assert ("remote.worker_alive", 1, "remote") in calls
        pipe = CollectingPipeline()
        from SciQLop.components.plotting.backend.remote.channel import RemoteChannel
        ch = RemoteChannel(pipeline=pipe, channel_id=1, transport=worker)
        worker.register_channel(ch)
        worker.install(1, cloudpickle.dumps(_sin_source), arity=2)

        calls.clear()
        ch.on_data_requested_values(0.0, 6.28)
        pending_after_send = [v for n, v, c in calls if n == "remote.pending_requests"]
        assert pending_after_send and pending_after_send[-1] == 1

        qtbot.waitUntil(lambda: len(pipe.results) == 1, timeout=15000)
        names = [c[0] for c in calls]
        assert "remote.last_latency_ms" in names
        pending_after_reply = [v for n, v, c in calls if n == "remote.pending_requests"]
        assert pending_after_reply[-1] == 0
    finally:
        worker.shutdown()
        assert ("remote.worker_alive", 0, "remote") in calls
