import cloudpickle
import numpy as np
import pytest
from SciQLop.components.plotting.backend.remote.worker_handle import RemoteWorker
from SciQLop.components.plotting.backend.remote.channel import RemoteChannel


class _Pipe:
    def set_data(self, *views):
        pass


def _src(s, e):
    return (np.array([s, e]), np.array([1.0, 2.0]))


def test_dispose_releases_without_touching_graph(qtbot):
    worker = RemoteWorker(plugin_key="t")
    worker.start()
    try:
        ch = RemoteChannel(pipeline=_Pipe(), channel_id=1, transport=worker)
        worker.register_channel(ch)
        worker.install(1, cloudpickle.dumps(_src), 2)
        ch.on_data_requested_values(0.0, 1.0)
        ch.dispose()                       # must not raise
        assert 1 not in worker._channels
    finally:
        worker.shutdown()


def test_worker_death_is_survived(qtbot):
    worker = RemoteWorker(plugin_key="t")
    worker.start()
    worker._proc.kill()                    # hard kill mid-life
    worker._proc.wait()
    worker._on_readable()                  # next readable event sees EOF; must not raise
    assert worker._proc is None
