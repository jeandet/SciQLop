import numpy as np
from multiprocessing import shared_memory
from SciQLop.components.plotting.backend.remote.protocol import pack_arrays, total_nbytes
import SciQLop.components.plotting.backend.remote.channel as channel_module
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
    def send_request(self, channel_id, req_id, start, stop, knobs):
        self.requests.append((channel_id, req_id, start, stop, knobs))
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


def test_duplicate_result_for_held_segment_is_not_freed():
    # A re-delivered RESULT naming the segment we currently hold must not be
    # FREEd back to the worker — it is still the live buffer SciQLopPlots reads.
    pipe, t = FakePipeline(), FakeTransport()
    ch = RemoteChannel(pipeline=pipe, channel_id=5, transport=t)
    ch.on_data_requested_values(0.0, 1.0)   # req 1 -> latest
    n1, l1, s1 = _make_segment([np.array([0.0]), np.array([1.0])])
    ch.on_result(1, n1, l1, 2)              # accept, held = n1
    ch.on_result(1, n1, l1, 2)              # duplicate, same segment, req_id == latest
    assert (5, n1) not in t.frees           # the held/live segment must NOT be freed
    s1.unlink()


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


def test_set_knobs_is_included_in_next_request():
    t = FakeTransport()
    ch = RemoteChannel(pipeline=FakePipeline(), channel_id=5, transport=t)
    ch.set_knobs({"gain": 2.0})
    ch.on_data_requested_values(0.0, 1.0)
    assert t.requests[-1] == (5, 1, 0.0, 1.0, {"gain": 2.0})


def test_default_knobs_is_empty_dict():
    t = FakeTransport()
    ch = RemoteChannel(pipeline=FakePipeline(), channel_id=5, transport=t)
    ch.on_data_requested_values(0.0, 1.0)
    assert t.requests[-1] == (5, 1, 0.0, 1.0, {})


class _FakeAsyncTracer:
    def __init__(self, monkeypatch):
        self.begins = []
        self.ends = []
        self._next_handle = 0
        monkeypatch.setattr(channel_module.tracing, "async_begin", self._begin)
        monkeypatch.setattr(channel_module.tracing, "async_end", self._end)

    def _begin(self, name, cat=""):
        self._next_handle += 1
        self.begins.append((self._next_handle, name, cat))
        return self._next_handle

    def _end(self, handle):
        self.ends.append(handle)


def test_async_span_opens_on_request_and_closes_on_result(monkeypatch):
    tracer = _FakeAsyncTracer(monkeypatch)
    pipe, t = FakePipeline(), FakeTransport()
    ch = RemoteChannel(pipeline=pipe, channel_id=5, transport=t)
    ch.on_data_requested_values(0.0, 1.0)
    assert len(tracer.begins) == 1
    assert tracer.ends == []
    n1, l1, s1 = _make_segment([np.array([0.0]), np.array([1.0])])
    ch.on_result(1, n1, l1, 2)
    assert tracer.ends == [tracer.begins[0][0]]
    s1.unlink()


def test_async_span_closes_on_empty(monkeypatch):
    tracer = _FakeAsyncTracer(monkeypatch)
    ch = RemoteChannel(pipeline=FakePipeline(), channel_id=5, transport=FakeTransport())
    ch.on_data_requested_values(0.0, 1.0)
    ch.on_empty(1)
    assert tracer.ends == [tracer.begins[0][0]]


def test_async_span_closes_on_error(monkeypatch):
    tracer = _FakeAsyncTracer(monkeypatch)
    ch = RemoteChannel(pipeline=FakePipeline(), channel_id=5, transport=FakeTransport())
    ch.on_data_requested_values(0.0, 1.0)
    ch.on_error(1, "boom")
    assert tracer.ends == [tracer.begins[0][0]]


def test_superseding_request_closes_previous_async_span(monkeypatch):
    tracer = _FakeAsyncTracer(monkeypatch)
    ch = RemoteChannel(pipeline=FakePipeline(), channel_id=5, transport=FakeTransport())
    ch.on_data_requested_values(0.0, 1.0)   # req 1, never resolved
    ch.on_data_requested_values(1.0, 2.0)   # supersedes req 1
    assert len(tracer.begins) == 2
    assert tracer.ends == [tracer.begins[0][0]]   # req 1's span closed, req 2's still open
    ch.on_empty(2)
    assert tracer.ends == [tracer.begins[0][0], tracer.begins[1][0]]
