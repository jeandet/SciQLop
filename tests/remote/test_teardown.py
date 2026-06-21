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


def test_start_times_out_if_worker_never_connects(monkeypatch, qtbot):
    import sys
    from SciQLop.components.plotting.backend.remote import worker_handle as wh
    real_popen = wh.subprocess.Popen

    def fake_popen(args, **kwargs):  # launch a process that never connects back
        return real_popen(
            [sys.executable, "-c", "import sys,time; sys.stdin.read(); time.sleep(30)"],
            **kwargs)

    monkeypatch.setattr(wh.subprocess, "Popen", fake_popen)
    w = wh.RemoteWorker(plugin_key="t")
    w._accept_timeout = 1.0
    with pytest.raises(RuntimeError, match="did not connect"):
        w.start()
    # the UI is not frozen and no live handle is left behind
    assert w._proc is None


def test_worker_death_is_survived(qtbot):
    worker = RemoteWorker(plugin_key="t")
    worker.start()
    worker._proc.kill()                    # hard kill mid-life
    worker._proc.wait()
    worker._on_readable()                  # next readable event sees EOF; must not raise
    assert worker._proc is None
