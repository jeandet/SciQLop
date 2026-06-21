import numpy as np
from multiprocessing import shared_memory
from SciQLop.components.plotting.backend.remote.protocol import pack_arrays, total_nbytes
from SciQLop.components.plotting.backend.remote.channel import RemoteChannel


class FakePipeline:
    def __init__(self):
        self.calls = []
    def set_data(self, *views):
        # copy out — views alias shm that may be freed later
        self.calls.append([np.array(v) for v in views])


class FakeTransport:
    def __init__(self):
        self.requests = []
        self.frees = []
    def send_request(self, channel_id, req_id, start, stop):
        self.requests.append((channel_id, req_id, start, stop))
    def send_free(self, channel_id, name):
        self.frees.append((channel_id, name))
    def release(self, channel_id):
        pass


def _make_segment(arrays):
    nbytes = total_nbytes(arrays)
    shm = shared_memory.SharedMemory(create=True, size=nbytes, track=False)
    layout = pack_arrays(shm.buf, arrays)
    return shm.name, layout, shm  # keep shm alive in caller


def test_data_requested_assigns_monotonic_req_ids():
    t = FakeTransport()
    ch = RemoteChannel(pipeline=FakePipeline(), channel_id=5, transport=t)
    ch.on_data_requested_values(0.0, 1.0)
    ch.on_data_requested_values(1.0, 2.0)
    assert [r[1] for r in t.requests] == [1, 2]


def test_current_result_sets_data_and_frees_previous_on_supersede():
    pipe, t = FakePipeline(), FakeTransport()
    ch = RemoteChannel(pipeline=pipe, channel_id=5, transport=t)
    ch.on_data_requested_values(0.0, 1.0)  # req 1 -> latest
    n1, l1, s1 = _make_segment([np.array([0.0, 1.0]), np.array([1.0])])
    n2, l2, s2 = _make_segment([np.array([1.0, 2.0]), np.array([2.0])])
    ch.on_result(1, n1, l1, 1)
    assert t.frees == []                    # nothing to supersede yet
    ch.on_data_requested_values(1.0, 2.0)  # req 2 -> latest
    ch.on_result(2, n2, l2, 2)
    assert (5, n1) in t.frees               # first segment released
    assert len(pipe.calls) == 2
    s1.unlink(); s2.unlink()


def test_stale_result_is_dropped_and_immediately_freed():
    pipe, t = FakePipeline(), FakeTransport()
    ch = RemoteChannel(pipeline=pipe, channel_id=5, transport=t)
    ch.on_data_requested_values(0.0, 1.0)  # req 1
    ch.on_data_requested_values(1.0, 2.0)  # req 2 -> latest
    n1, l1, s1 = _make_segment([np.array([0.0]), np.array([1.0])])
    ch.on_result(1, n1, l1, 2)              # stale (1 < 2)
    assert pipe.calls == []                 # never set_data
    assert (5, n1) in t.frees               # freed immediately
    s1.unlink()
