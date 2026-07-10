import threading
import numpy as np
import cloudpickle
from multiprocessing import Pipe
from multiprocessing import shared_memory
from SciQLop.components.plotting.backend.remote import protocol as P
from SciQLop.components.plotting.backend.remote.protocol import unpack_arrays
from SciQLop.components.plotting.backend.remote.worker import serve, _coalesce, _WorkerState


def _run_worker(conn):
    t = threading.Thread(target=serve, args=(conn,), daemon=True)
    t.start()
    return t


def test_request_returns_result_with_readable_arrays():
    main, worker = Pipe()
    _run_worker(worker)
    cb = lambda start, stop: (np.array([start, stop]), np.array([1.0, 2.0]))
    main.send((P.INSTALL, 1, cloudpickle.dumps(cb), 2))
    main.send((P.REQUEST, 1, 1, 0.0, 10.0, {}))
    tag, ch, req, name, layout, arity = main.recv()
    assert (tag, ch, req, arity) == (P.RESULT, 1, 1, 2)
    shm = shared_memory.SharedMemory(name=name, track=False)
    x, y = unpack_arrays(shm.buf, layout)
    np.testing.assert_array_equal(x, [0.0, 10.0])
    np.testing.assert_array_equal(y, [1.0, 2.0])
    shm.close()
    main.send((P.SHUTDOWN,))


def test_callback_returning_none_yields_empty():
    main, worker = Pipe()
    _run_worker(worker)
    main.send((P.INSTALL, 1, cloudpickle.dumps(lambda s, e: None), 2))
    main.send((P.REQUEST, 1, 7, 0.0, 1.0, {}))
    assert main.recv() == (P.EMPTY, 1, 7)
    main.send((P.SHUTDOWN,))


def test_callback_raising_yields_error_with_traceback():
    main, worker = Pipe()
    _run_worker(worker)
    def boom(s, e):
        raise ValueError("kaboom")
    main.send((P.INSTALL, 1, cloudpickle.dumps(boom), 2))
    main.send((P.REQUEST, 1, 3, 0.0, 1.0, {}))
    tag, ch, req, tb = main.recv()
    assert (tag, ch, req) == (P.ERROR, 1, 3)
    assert "kaboom" in tb
    main.send((P.SHUTDOWN,))


def test_coalesce_keeps_latest_knobs_with_latest_request():
    state = _WorkerState()
    msgs = [
        (P.REQUEST, 1, 1, 0.0, 1.0, {"gain": 1.0}),
        (P.REQUEST, 1, 2, 0.0, 2.0, {"gain": 2.0}),
    ]
    latest = _coalesce(msgs, state, conn=None)
    assert latest == {1: (2, 0.0, 2.0, {"gain": 2.0})}


def test_two_channels_get_non_colliding_shm_segment_names():
    """Two channels on the same worker each get their own ShmPool
    (_WorkerState.pool(channel_id)); each pool's internal counter starts at
    0, so their first-ever segment must not collide on name within the
    shared worker process (same pid). Reproduces a real crash: two synced
    remote graphs on one worker both requesting data concurrently hit
    FileExistsError on shared_memory.SharedMemory(create=True) for the same
    name, which is unhandled in _serve_request and kills the whole worker."""
    state = _WorkerState()
    seg1 = state.pool(1).acquire(64)
    try:
        seg2 = state.pool(2).acquire(64)
        try:
            assert seg1.name != seg2.name
        finally:
            seg2.shm.close()
            seg2.shm.unlink()
    finally:
        seg1.shm.close()
        seg1.shm.unlink()


def test_worker_applies_knobs_to_callback():
    main, worker = Pipe()
    _run_worker(worker)
    def scaled(start, stop, gain=1.0):
        return (np.array([start, stop]), np.array([1.0, 2.0]) * gain)
    main.send((P.INSTALL, 1, cloudpickle.dumps(scaled), 2))
    main.send((P.REQUEST, 1, 1, 0.0, 10.0, {"gain": 3.0}))
    tag, ch, req, name, layout, arity = main.recv()
    assert (tag, ch, req, arity) == (P.RESULT, 1, 1, 2)
    shm = shared_memory.SharedMemory(name=name, track=False)
    x, y = unpack_arrays(shm.buf, layout)
    np.testing.assert_array_equal(y, [3.0, 6.0])
    shm.close()
    main.send((P.SHUTDOWN,))
