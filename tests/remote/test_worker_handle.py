import numpy as np
import cloudpickle
import pytest
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
