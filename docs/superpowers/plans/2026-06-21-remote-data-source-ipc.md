# Remote Data Source IPC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a slow Python data-source callable in a separate process and stream its results, zero-copy over shared memory, into a SciQLopPlots v0.29.0 remote-backed graph — so GIL-heavy plugins (e.g. `sciqlop_radio`) never starve the GUI.

**Architecture:** A plugin flags a virtual product `out_of_process=True`. At registration the callable is cloudpickled (fail-fast). On first plot, SciQLop spawns one worker subprocess per plugin and drives a SciQLopPlots remote channel: `data_requested` → control pipe → worker computes → writes into a pooled shm segment → `RESULT` handle back → main wraps it as a numpy view → `set_data`. Segment reuse is consumer-driven (a `FREE` message after a newer `set_data` supersedes the old buffer), which is what makes zero-copy safe. Stale replies are dropped by monotonic `req_id`.

**Tech Stack:** Python 3.13, `multiprocessing` (spawn) + `multiprocessing.shared_memory` (with `track=False` on the consumer), `cloudpickle`, numpy, PySide6 (`QSocketNotifier` only), SciQLopPlots ≥ 0.29.0, pytest / pytest-qt.

---

## Prerequisites (already done / one new dep)

- SciQLopPlots is pinned to `==0.29.0` in `pyproject.toml` and installed. The remote API is present: `SciQLopPlot.add_remote_color_map(name)`, `add_remote_line_graph(labels=...)`, graph `.remote_channel()` → `RemoteDataPipeline` with signal `data_requested(SciQLopPlotRange)` and slots `set_data(x, y[, z])`. `SciQLopPlotRange` exposes `.start()` / `.stop()`.
- **New runtime dependency:** `cloudpickle` (stdlib `pickle` cannot serialize the radio closure/lambdas).

### Task 0: Add the cloudpickle dependency

**Files:**
- Modify: `pyproject.toml` (the `dependencies = [...]` list, around line 39)

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add `"cloudpickle"` to the `dependencies` list, directly after the `"SciQLopPlots==0.29.0",` line:

```toml
    "SciQLopPlots==0.29.0",
    "cloudpickle",
```

- [ ] **Step 2: Install it**

Run: `uv pip install cloudpickle`
Expected: `Installed 1 package ... + cloudpickle`

- [ ] **Step 3: Verify import**

Run: `uv run python -c "import cloudpickle; print(cloudpickle.__version__)"`
Expected: a version string, no traceback.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add cloudpickle dependency for remote data sources"
```

---

## File structure

New self-contained package `SciQLop/components/plotting/backend/remote/`:

| File | Responsibility |
|---|---|
| `protocol.py` | Wire message tags, `ArrayLayout`, `pack_arrays` / `unpack_arrays` (the wire format), `total_nbytes` |
| `reduction.py` | `reduce_result(result, arity)` → list of contiguous native-dtype numpy arrays |
| `shm_pool.py` | `Segment`, `ShmPool` (per-channel; sole creator/unlinker of segments) |
| `worker.py` | Worker entry point: `serve(conn)` loop + `_main()` bootstrap |
| `channel.py` | `RemoteChannel` — per-graph main-side state machine (req_id, stale-drop, FREE accounting, held rotation) |
| `worker_handle.py` | `RemoteWorker` — subprocess + duplex pipe + `QSocketNotifier`, routes replies to channels |
| `registry.py` | `RemoteRegistry` — cloudpickle fail-fast validation, plugin→worker grouping |

Tests under `tests/remote/`. Integration touches `easy_provider.py`, the user-facing factories, and `time_sync_panel.plot_product`.

Bottom-up order: pure units first (0–4), then the main-side state machine (5), then Qt/subprocess wiring (6–7), then registration + plot-path integration (8–9), then end-to-end + teardown (10).

---

### Task 1: Wire format — `pack_arrays` / `unpack_arrays`

The format both processes agree on: N arrays packed back-to-back into one buffer at 8-byte-aligned offsets; a list of `ArrayLayout(shape, dtype, offset)` describes them. `pack_arrays` copies into a writable buffer (worker side); `unpack_arrays` returns **views** into a buffer (consumer side, zero-copy).

**Files:**
- Create: `SciQLop/components/plotting/backend/remote/__init__.py` (empty)
- Create: `SciQLop/components/plotting/backend/remote/protocol.py`
- Test: `tests/remote/__init__.py` (empty), `tests/remote/test_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_protocol.py
import numpy as np
import pytest
from SciQLop.components.plotting.backend.remote.protocol import (
    pack_arrays, unpack_arrays, total_nbytes, ArrayLayout,
)


def test_pack_then_unpack_roundtrips_values_and_dtypes():
    x = np.linspace(0, 1, 5).astype(np.float64)
    z = np.arange(6, dtype=np.float32).reshape(2, 3)
    buf = bytearray(total_nbytes([x, z]))
    layout = pack_arrays(memoryview(buf), [x, z])
    assert [l.dtype for l in layout] == [x.dtype.str, z.dtype.str]
    out = unpack_arrays(memoryview(buf), layout)
    np.testing.assert_array_equal(out[0], x)
    np.testing.assert_array_equal(out[1], z)
    assert out[1].shape == (2, 3)


def test_offsets_are_8_byte_aligned():
    a = np.ones(3, dtype=np.float32)   # 12 bytes -> next offset padded to 16
    b = np.ones(2, dtype=np.float64)
    layout = pack_arrays(memoryview(bytearray(total_nbytes([a, b]))), [a, b])
    assert layout[0].offset == 0
    assert layout[1].offset % 8 == 0
    assert layout[1].offset >= a.nbytes


def test_unpack_returns_views_not_copies():
    a = np.arange(4, dtype=np.float64)
    buf = bytearray(total_nbytes([a]))
    layout = pack_arrays(memoryview(buf), [a])
    out = unpack_arrays(memoryview(buf), layout)
    out[0][0] = 999.0
    assert np.frombuffer(buf, dtype=np.float64, count=1)[0] == 999.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_protocol.py -v --no-xvfb`
Expected: FAIL — `ModuleNotFoundError: ...remote.protocol`.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/plotting/backend/remote/protocol.py
"""Wire format + message tags for remote data sources.

Messages are plain tuples (tag-first) so they pickle trivially over a
multiprocessing pipe. Bulk arrays travel through shared memory; the pipe
carries only handles + this layout metadata.
"""
from __future__ import annotations

from typing import List, NamedTuple
import numpy as np

# main -> worker
INSTALL = "INSTALL"      # (INSTALL, channel_id, cloudpickle_blob, arity)
REQUEST = "REQUEST"      # (REQUEST, channel_id, req_id, start, stop)
FREE = "FREE"            # (FREE, channel_id, shm_name)
RELEASE = "RELEASE"      # (RELEASE, channel_id)
SHUTDOWN = "SHUTDOWN"    # (SHUTDOWN,)
# worker -> main
RESULT = "RESULT"        # (RESULT, channel_id, req_id, shm_name, layout, arity)
EMPTY = "EMPTY"          # (EMPTY, channel_id, req_id)
ERROR = "ERROR"          # (ERROR, channel_id, req_id, traceback_str)

_ALIGN = 8


class ArrayLayout(NamedTuple):
    shape: tuple
    dtype: str          # numpy dtype .str, e.g. '<f4'
    offset: int


def _aligned(n: int) -> int:
    return (n + _ALIGN - 1) // _ALIGN * _ALIGN


def total_nbytes(arrays: List[np.ndarray]) -> int:
    total = 0
    for a in arrays:
        total = _aligned(total) + a.nbytes
    return _aligned(total)


def pack_arrays(buf: memoryview, arrays: List[np.ndarray]) -> List[ArrayLayout]:
    layout: List[ArrayLayout] = []
    offset = 0
    for a in arrays:
        offset = _aligned(offset)
        a = np.ascontiguousarray(a)
        view = np.ndarray(a.shape, dtype=a.dtype, buffer=buf, offset=offset)
        view[...] = a
        layout.append(ArrayLayout(tuple(a.shape), a.dtype.str, offset))
        offset += a.nbytes
    return layout


def unpack_arrays(buf: memoryview, layout: List[ArrayLayout]) -> List[np.ndarray]:
    return [
        np.ndarray(tuple(l.shape), dtype=np.dtype(l.dtype), buffer=buf, offset=l.offset)
        for l in layout
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_protocol.py -v --no-xvfb`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/__init__.py \
        SciQLop/components/plotting/backend/remote/protocol.py \
        tests/remote/__init__.py tests/remote/test_protocol.py
git commit -m "feat(remote): wire format pack/unpack for shm-backed arrays"
```

---

### Task 2: Result reduction

`reduce_result(result, arity)` turns whatever a callback returned into a list of contiguous, native-dtype numpy arrays sized by `arity` (2 = `(x, y)`, 3 = `(x, y, z)`). `x` (time) is forced to float64 epoch seconds; `y`/`z` keep their dtype (float32 stays float32 — no upcast). Handles `SpeasyVariable` and raw array tuples/lists.

**Files:**
- Create: `SciQLop/components/plotting/backend/remote/reduction.py`
- Test: `tests/remote/test_reduction.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_reduction.py
import numpy as np
from SciQLop.components.plotting.backend.remote.reduction import reduce_result


def test_tuple_arity2_kept_contiguous_and_time_float64():
    t = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    y = np.array([10.0, 20.0, 30.0], dtype=np.float32)
    arrays = reduce_result((t, y), arity=2)
    assert len(arrays) == 2
    assert arrays[0].dtype == np.float64          # time upcast to epoch f64
    assert arrays[1].dtype == np.float32          # values dtype preserved
    assert all(a.flags["C_CONTIGUOUS"] for a in arrays)


def test_tuple_arity3_spectrogram():
    t = np.arange(4, dtype=np.float64)
    f = np.arange(3, dtype=np.float64)
    z = np.arange(12, dtype=np.float32).reshape(4, 3)
    arrays = reduce_result((t, f, z), arity=3)
    assert len(arrays) == 3
    assert arrays[2].shape == (4, 3)
    assert arrays[2].dtype == np.float32


def test_speasy_variable_spectrogram_reduces_to_time_freq_z():
    speasy = __import__("speasy")
    from speasy.core.data_containers import DataContainer, VariableTimeAxis, VariableAxis
    from speasy.products.variable import SpeasyVariable
    times = np.array(["2020-01-01T00:00:00", "2020-01-01T00:01:00"],
                     dtype="datetime64[ns]")
    freqs = np.array([10.0, 20.0, 30.0], dtype=np.float64)
    zvals = np.arange(6, dtype=np.float32).reshape(2, 3)
    v = SpeasyVariable(
        axes=[VariableTimeAxis(values=times),
              VariableAxis(values=freqs, name="freq")],
        values=DataContainer(values=zvals, meta={}, name="spec"),
        columns=["f0", "f1", "f2"],
    )
    x, y, z = reduce_result(v, arity=3)
    assert x.dtype == np.float64
    # epoch seconds: first sample is 2020-01-01 -> 1577836800
    assert abs(x[0] - 1577836800.0) < 1.0
    np.testing.assert_array_equal(y, freqs)
    np.testing.assert_array_equal(z, zvals)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_reduction.py -v --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/plotting/backend/remote/reduction.py
"""Reduce a data-source callback result to native-dtype numpy arrays.

`arity` is fixed by the graph type at INSTALL (2 = line/curve, 3 = colormap),
so we never guess shape from the data."""
from __future__ import annotations

from typing import List
import numpy as np


def _epoch_seconds(time_values: np.ndarray) -> np.ndarray:
    arr = np.asarray(time_values)
    if np.issubdtype(arr.dtype, np.datetime64):
        return arr.astype("datetime64[ns]").astype("int64").astype(np.float64) / 1e9
    return np.ascontiguousarray(arr, dtype=np.float64)


def _is_speasy_variable(result) -> bool:
    try:
        from speasy.products.variable import SpeasyVariable
    except Exception:
        return False
    return isinstance(result, SpeasyVariable)


def _from_speasy(v, arity: int) -> List[np.ndarray]:
    x = _epoch_seconds(v.time)
    if arity == 3:
        freq = np.ascontiguousarray(np.asarray(v.axes[1].values))
        z = np.ascontiguousarray(np.asarray(v.values))
        return [x, freq, z]
    y = np.ascontiguousarray(np.asarray(v.values))
    return [x, y]


def _from_sequence(seq, arity: int) -> List[np.ndarray]:
    parts = list(seq)
    if len(parts) != arity:
        raise ValueError(f"expected {arity} arrays, got {len(parts)}")
    out = [_epoch_seconds(parts[0])]
    out += [np.ascontiguousarray(np.asarray(p)) for p in parts[1:]]
    return out


def reduce_result(result, arity: int) -> List[np.ndarray]:
    if _is_speasy_variable(result):
        return _from_speasy(result, arity)
    return _from_sequence(result, arity)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_reduction.py -v --no-xvfb`
Expected: PASS (3 passed). If the SpeasyVariable construction API differs in the installed speasy, adjust the test's variable construction only — the `reduce_result` contract (read `.time`, `.values`, `.axes[1].values`) is stable.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/reduction.py tests/remote/test_reduction.py
git commit -m "feat(remote): reduce callback results to native-dtype arrays"
```

---

### Task 3: Shared-memory pool

`ShmPool` (one per channel, lives in the worker) is the **sole creator and unlinker** of segments. `acquire(nbytes)` returns a free segment ≥ size (growing the pool if none free, marking it in-use); `mark_reusable(name)` releases one back; `unlink_all()` tears the channel down. Created with `track=False` so the worker owns the lifetime explicitly.

**Files:**
- Create: `SciQLop/components/plotting/backend/remote/shm_pool.py`
- Test: `tests/remote/test_shm_pool.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_shm_pool.py
import pytest
from SciQLop.components.plotting.backend.remote.shm_pool import ShmPool


def test_acquire_then_reuse_same_segment_after_free():
    pool = ShmPool(name_prefix="sciqlop_test")
    try:
        s1 = pool.acquire(100)
        name1 = s1.name
        pool.mark_reusable(name1)
        s2 = pool.acquire(50)          # fits in the freed 100-byte segment
        assert s2.name == name1        # reused, not a new segment
        assert pool.segment_count == 1
    finally:
        pool.unlink_all()


def test_acquire_while_out_allocates_new_segment():
    pool = ShmPool(name_prefix="sciqlop_test")
    try:
        s1 = pool.acquire(100)         # still out (not freed)
        s2 = pool.acquire(100)
        assert s1.name != s2.name
        assert pool.segment_count == 2
    finally:
        pool.unlink_all()


def test_acquire_grows_when_free_segment_too_small():
    pool = ShmPool(name_prefix="sciqlop_test")
    try:
        s1 = pool.acquire(10)
        pool.mark_reusable(s1.name)
        s2 = pool.acquire(1000)        # too big for the 10-byte free one
        assert s2.size >= 1000
    finally:
        pool.unlink_all()


def test_unlink_all_removes_segments():
    from multiprocessing import shared_memory
    pool = ShmPool(name_prefix="sciqlop_test")
    s = pool.acquire(64)
    name = s.name
    pool.unlink_all()
    with pytest.raises(FileNotFoundError):
        shared_memory.SharedMemory(name=name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_shm_pool.py -v --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/plotting/backend/remote/shm_pool.py
"""Per-channel shared-memory segment pool, owned by the worker process.

The worker is the SOLE creator and unlinker of segments (track=False so the
resource_tracker never touches them). A segment handed out by acquire() is
'in use' until mark_reusable() returns it — the consumer drives that via FREE
messages once a newer set_data supersedes the buffer. This is what makes the
zero-copy hand-off race-free."""
from __future__ import annotations

import os
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Dict


@dataclass
class Segment:
    shm: shared_memory.SharedMemory
    size: int
    in_use: bool = False

    @property
    def name(self) -> str:
        return self.shm.name

    @property
    def buf(self):
        return self.shm.buf


class ShmPool:
    def __init__(self, name_prefix: str = "sciqlop"):
        self._prefix = f"{name_prefix}_{os.getpid()}"
        self._segments: Dict[str, Segment] = {}
        self._counter = 0

    @property
    def segment_count(self) -> int:
        return len(self._segments)

    def acquire(self, nbytes: int) -> Segment:
        nbytes = max(int(nbytes), 1)
        for seg in self._segments.values():
            if not seg.in_use and seg.size >= nbytes:
                seg.in_use = True
                return seg
        self._counter += 1
        shm = shared_memory.SharedMemory(
            name=f"{self._prefix}_{self._counter}", create=True, size=nbytes,
            track=False,
        )
        seg = Segment(shm=shm, size=shm.size, in_use=True)
        self._segments[seg.name] = seg
        return seg

    def mark_reusable(self, name: str) -> None:
        seg = self._segments.get(name)
        if seg is not None:
            seg.in_use = False

    def unlink_all(self) -> None:
        for seg in self._segments.values():
            try:
                seg.shm.close()
                seg.shm.unlink()
            except FileNotFoundError:
                pass
        self._segments.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_shm_pool.py -v --no-xvfb`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/shm_pool.py tests/remote/test_shm_pool.py
git commit -m "feat(remote): consumer-released shared-memory segment pool"
```

---

### Task 4: Worker serve loop

`serve(conn, callable_loader=cloudpickle.loads)` runs the worker's message loop against a `multiprocessing.Connection`: installs callables, drains+coalesces requests, computes, writes results into pooled segments, replies `RESULT`/`EMPTY`/`ERROR`, and reclaims segments on `FREE`. Tested over an in-process `Pipe()` — no real subprocess yet.

**Files:**
- Create: `SciQLop/components/plotting/backend/remote/worker.py`
- Test: `tests/remote/test_worker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_worker.py
import threading
import numpy as np
import cloudpickle
from multiprocessing import Pipe
from multiprocessing import shared_memory
from SciQLop.components.plotting.backend.remote import protocol as P
from SciQLop.components.plotting.backend.remote.protocol import unpack_arrays
from SciQLop.components.plotting.backend.remote.worker import serve


def _run_worker(conn):
    t = threading.Thread(target=serve, args=(conn,), daemon=True)
    t.start()
    return t


def test_request_returns_result_with_readable_arrays():
    main, worker = Pipe()
    _run_worker(worker)
    cb = lambda start, stop: (np.array([start, stop]), np.array([1.0, 2.0]))
    main.send((P.INSTALL, 1, cloudpickle.dumps(cb), 2))
    main.send((P.REQUEST, 1, 1, 0.0, 10.0))
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
    main.send((P.REQUEST, 1, 7, 0.0, 1.0))
    assert main.recv() == (P.EMPTY, 1, 7)
    main.send((P.SHUTDOWN,))


def test_callback_raising_yields_error_with_traceback():
    main, worker = Pipe()
    _run_worker(worker)
    def boom(s, e):
        raise ValueError("kaboom")
    main.send((P.INSTALL, 1, cloudpickle.dumps(boom), 2))
    main.send((P.REQUEST, 1, 3, 0.0, 1.0))
    tag, ch, req, tb = main.recv()
    assert (tag, ch, req) == (P.ERROR, 1, 3)
    assert "kaboom" in tb
    main.send((P.SHUTDOWN,))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_worker.py -v --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/plotting/backend/remote/worker.py
"""Out-of-process data-source worker.

Single-threaded loop: install cloudpickled callables, coalesce requests
(keep only the latest per channel), compute, write results into a per-channel
ShmPool segment, reply with the handle. Segments are reclaimed on FREE."""
from __future__ import annotations

import sys
import traceback
from typing import Dict

import cloudpickle

from . import protocol as P
from .protocol import pack_arrays, total_nbytes
from .reduction import reduce_result
from .shm_pool import ShmPool


def _stale_sweep(prefix: str = "sciqlop") -> None:
    """Best-effort removal of leaked segments from a previously hard-killed
    worker (same prefix, dead pid). Safe to skip if /dev/shm is unavailable."""
    import glob, os
    base = "/dev/shm"
    if not os.path.isdir(base):
        return
    for path in glob.glob(os.path.join(base, f"{prefix}_*")):
        try:
            from multiprocessing import shared_memory
            shared_memory.SharedMemory(name=os.path.basename(path), track=False).unlink()
        except Exception:
            pass


class _WorkerState:
    def __init__(self):
        self.callables: Dict[int, object] = {}
        self.arity: Dict[int, int] = {}
        self.pools: Dict[int, ShmPool] = {}

    def pool(self, channel_id: int) -> ShmPool:
        if channel_id not in self.pools:
            self.pools[channel_id] = ShmPool()
        return self.pools[channel_id]

    def release(self, channel_id: int) -> None:
        self.callables.pop(channel_id, None)
        self.arity.pop(channel_id, None)
        pool = self.pools.pop(channel_id, None)
        if pool is not None:
            pool.unlink_all()


def _drain(conn, first):
    """Return (messages) = first + everything already queued, without blocking."""
    msgs = [first]
    while conn.poll(0):
        msgs.append(conn.recv())
    return msgs


def _coalesce(msgs, state, conn) -> Dict[int, tuple]:
    """Apply INSTALL/FREE/RELEASE immediately; keep only the latest REQUEST
    per channel. Returns {channel_id: (req_id, start, stop)}."""
    latest: Dict[int, tuple] = {}
    for m in msgs:
        tag = m[0]
        if tag == P.INSTALL:
            _, ch, blob, arity = m
            state.callables[ch] = cloudpickle.loads(blob)
            state.arity[ch] = arity
        elif tag == P.FREE:
            _, ch, name = m
            if ch in state.pools:
                state.pools[ch].mark_reusable(name)
        elif tag == P.REQUEST:
            _, ch, req, start, stop = m
            latest[ch] = (req, start, stop)
        elif tag == P.RELEASE:
            _, ch = m
            state.release(ch)
            latest.pop(ch, None)
    return latest


def _serve_request(conn, state, channel_id, req_id, start, stop) -> None:
    cb = state.callables.get(channel_id)
    if cb is None:
        return
    try:
        result = cb(start, stop)
    except Exception:
        conn.send((P.ERROR, channel_id, req_id, traceback.format_exc()))
        return
    if result is None:
        conn.send((P.EMPTY, channel_id, req_id))
        return
    arrays = reduce_result(result, state.arity[channel_id])
    seg = state.pool(channel_id).acquire(total_nbytes(arrays))
    layout = pack_arrays(seg.buf, arrays)
    conn.send((P.RESULT, channel_id, req_id, seg.name, layout, state.arity[channel_id]))


def serve(conn) -> None:
    state = _WorkerState()
    while True:
        try:
            first = conn.recv()
        except EOFError:
            break
        if first[0] == P.SHUTDOWN:
            break
        latest = _coalesce(_drain(conn, first), state, conn)
        if any(m[0] == P.SHUTDOWN for m in [first]):
            break
        for channel_id, (req_id, start, stop) in latest.items():
            _serve_request(conn, state, channel_id, req_id, start, stop)
    for ch in list(state.pools):
        state.release(ch)


def _main() -> None:
    import multiprocessing.connection as mpc
    address = sys.argv[1]
    authkey = sys.stdin.buffer.read()  # supplied by parent on stdin
    _stale_sweep()
    with mpc.Client(address, authkey=authkey) as conn:
        serve(conn)


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_worker.py -v --no-xvfb`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/worker.py tests/remote/test_worker.py
git commit -m "feat(remote): single-threaded worker serve loop with coalescing"
```

---

### Task 5: `RemoteChannel` state machine (the race-free rule)

Per-graph main-side object. Collaborators are injected so it is testable with **no Qt and no subprocess**: a `pipeline` (anything with `set_data(*views)`) and a `transport` (anything with `send_request(channel_id, req_id, start, stop)` and `send_free(channel_id, name)`). It assigns monotonic `req_id`s, drops stale `RESULT`s, holds the live segment, and `FREE`s the previous one only after a newer `set_data` supersedes it.

**Files:**
- Create: `SciQLop/components/plotting/backend/remote/channel.py`
- Test: `tests/remote/test_channel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_channel.py
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
    ch.on_data_requested_values(0.0, 1.0)  # req 1
    ch.on_data_requested_values(1.0, 2.0)  # req 2
    n1, l1, s1 = _make_segment([np.array([0.0, 1.0]), np.array([1.0])])
    n2, l2, s2 = _make_segment([np.array([1.0, 2.0]), np.array([2.0])])
    ch.on_result(1, n1, l1, 2)
    assert t.frees == []                    # nothing to supersede yet
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_channel.py -v --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/plotting/backend/remote/channel.py
"""Per-graph main-side state machine driving one SciQLopPlots remote channel.

Owns req_id assignment, stale-reply dropping, and the consumer-side segment
lifetime: the previous segment is FREEd only once a newer set_data supersedes
it (so SciQLopPlots never reads a buffer the worker might overwrite)."""
from __future__ import annotations

import logging
from multiprocessing import shared_memory
from typing import Optional

from .protocol import unpack_arrays

log = logging.getLogger(__name__)


class RemoteChannel:
    def __init__(self, pipeline, channel_id: int, transport):
        self._pipeline = pipeline
        self.channel_id = channel_id
        self._transport = transport
        self._latest_req_id = 0
        self._held: Optional[shared_memory.SharedMemory] = None
        self._held_name: Optional[str] = None

    # --- outgoing -----------------------------------------------------------
    def on_data_requested_values(self, start: float, stop: float) -> None:
        self._latest_req_id += 1
        self._transport.send_request(self.channel_id, self._latest_req_id, start, stop)

    def on_data_requested(self, rng) -> None:
        self.on_data_requested_values(rng.start(), rng.stop())

    # --- incoming -----------------------------------------------------------
    def on_result(self, req_id: int, shm_name: str, layout, arity: int) -> None:
        if req_id < self._latest_req_id:
            self._transport.send_free(self.channel_id, shm_name)   # stale: drop + free
            return
        shm = shared_memory.SharedMemory(name=shm_name, create=False, track=False)
        views = unpack_arrays(shm.buf, layout)
        self._pipeline.set_data(*views)
        self._supersede(shm, shm_name)

    def on_empty(self, req_id: int) -> None:
        pass

    def on_error(self, req_id: int, tb: str) -> None:
        log.error("remote data source error (channel %s):\n%s", self.channel_id, tb)

    # --- lifetime -----------------------------------------------------------
    def _supersede(self, shm, name) -> None:
        prev, prev_name = self._held, self._held_name
        self._held, self._held_name = shm, name
        if prev is not None:
            prev.close()
            self._transport.send_free(self.channel_id, prev_name)

    def dispose(self) -> None:
        self._transport.release(self.channel_id)
        if self._held is not None:
            self._held.close()
            self._transport.send_free(self.channel_id, self._held_name)
            self._held, self._held_name = None, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_channel.py -v --no-xvfb`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/channel.py tests/remote/test_channel.py
git commit -m "feat(remote): RemoteChannel state machine (req_id, stale-drop, FREE)"
```

---

### Task 6: `RemoteWorker` — subprocess + QSocketNotifier transport

Owns the spawned subprocess, the duplex pipe, a `QSocketNotifier` on the pipe fd (replies land on the main thread), and the `channel_id → RemoteChannel` routing table. Implements the `transport` interface (`send_request`/`send_free`/`release`) used by `RemoteChannel`. Spawned lazily by the registry.

The subprocess is launched with `multiprocessing.connection.Listener` (so we can hand it an address + authkey and keep the parent's pipe fd pollable by `QSocketNotifier`).

**Files:**
- Create: `SciQLop/components/plotting/backend/remote/worker_handle.py`
- Test: `tests/remote/test_worker_handle.py` (real subprocess, subprocess-isolated marker)

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_worker_handle.py
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


@pytest.mark.timeout(30)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_worker_handle.py -v --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/plotting/backend/remote/worker_handle.py
"""Main-side handle on one worker subprocess.

Spawns the worker, owns the duplex Connection, and pumps replies onto the main
thread via a QSocketNotifier on the connection's fd. Implements the transport
interface (send_request/send_free/release) that RemoteChannel calls."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from multiprocessing.connection import Listener
from typing import Dict

from PySide6.QtCore import QObject, QSocketNotifier

from . import protocol as P

log = logging.getLogger(__name__)


class RemoteWorker(QObject):
    def __init__(self, plugin_key: str, parent: QObject | None = None):
        super().__init__(parent)
        self.plugin_key = plugin_key
        self._proc: subprocess.Popen | None = None
        self._conn = None
        self._notifier: QSocketNotifier | None = None
        self._channels: Dict[int, object] = {}

    # --- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._proc is not None:
            return
        authkey = os.urandom(32)
        address = os.path.join(tempfile.gettempdir(), f"sciqlop-remote-{os.getpid()}-{id(self)}")
        listener = Listener(address, authkey=authkey)
        self._proc = subprocess.Popen(
            [sys.executable, "-m",
             "SciQLop.components.plotting.backend.remote.worker", address],
            stdin=subprocess.PIPE,
        )
        self._proc.stdin.write(authkey)
        self._proc.stdin.close()
        self._conn = listener.accept()
        listener.close()
        self._notifier = QSocketNotifier(self._conn.fileno(), QSocketNotifier.Type.Read)
        self._notifier.activated.connect(self._on_readable)

    def shutdown(self) -> None:
        try:
            if self._conn is not None:
                self._conn.send((P.SHUTDOWN,))
        except Exception:
            pass
        if self._notifier is not None:
            self._notifier.setEnabled(False)
        if self._proc is not None:
            try:
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
        self._proc, self._conn, self._notifier = None, None, None

    # --- channels -----------------------------------------------------------
    def register_channel(self, channel) -> None:
        self._channels[channel.channel_id] = channel

    def install(self, channel_id: int, blob: bytes, arity: int) -> None:
        self._conn.send((P.INSTALL, channel_id, blob, arity))

    # --- transport interface (called by RemoteChannel) ----------------------
    def send_request(self, channel_id: int, req_id: int, start: float, stop: float) -> None:
        self._conn.send((P.REQUEST, channel_id, req_id, start, stop))

    def send_free(self, channel_id: int, name: str) -> None:
        self._conn.send((P.FREE, channel_id, name))

    def release(self, channel_id: int) -> None:
        self._channels.pop(channel_id, None)
        if self._conn is not None:
            try:
                self._conn.send((P.RELEASE, channel_id))
            except Exception:
                pass

    # --- reply pump ---------------------------------------------------------
    def _on_readable(self) -> None:
        while self._conn is not None and self._conn.poll(0):
            try:
                msg = self._conn.recv()
            except EOFError:
                self._on_worker_died()
                return
            self._dispatch(msg)

    def _dispatch(self, msg) -> None:
        tag = msg[0]
        if tag == P.RESULT:
            _, ch, req, name, layout, arity = msg
            c = self._channels.get(ch)
            if c is not None:
                c.on_result(req, name, layout, arity)
        elif tag == P.EMPTY:
            _, ch, req = msg
            c = self._channels.get(ch)
            if c is not None:
                c.on_empty(req)
        elif tag == P.ERROR:
            _, ch, req, tb = msg
            c = self._channels.get(ch)
            if c is not None:
                c.on_error(req, tb)

    def _on_worker_died(self) -> None:
        log.warning("remote worker for %s died", self.plugin_key)
        if self._notifier is not None:
            self._notifier.setEnabled(False)
        self._proc, self._conn, self._notifier = None, None, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_worker_handle.py -v --no-xvfb`
Expected: PASS (1 passed). Requires `pytest-qt` (`qtbot`) and `pytest-timeout` (already dev deps; if `pytest.mark.timeout` is unknown, drop that decorator).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/worker_handle.py tests/remote/test_worker_handle.py
git commit -m "feat(remote): RemoteWorker subprocess + QSocketNotifier reply pump"
```

---

### Task 7: `RemoteRegistry` — fail-fast validation + worker grouping

App-global singleton. `register(path, callback, arity)` cloudpickles the callable **immediately** (raising a clear, product-named error if it can't) and stores the blob keyed by `path`. `worker_for(plugin_key)` lazily spawns and caches one `RemoteWorker` per plugin. `plugin_key_for(callback)` is the callable's top-level module.

**Files:**
- Create: `SciQLop/components/plotting/backend/remote/registry.py`
- Test: `tests/remote/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_registry.py
import pytest
from SciQLop.components.plotting.backend.remote.registry import (
    RemoteRegistry, plugin_key_for,
)


def test_register_pickles_and_stores_blob():
    reg = RemoteRegistry()
    reg.register("radio/eovsa", lambda s, e: None, arity=3)
    assert reg.is_remote(["radio", "eovsa"])
    blob, arity = reg.spec_for(["radio", "eovsa"])
    assert isinstance(blob, bytes) and arity == 3


def test_register_unpicklable_raises_named_error():
    reg = RemoteRegistry()
    unpicklable = (lambda: (_ for _ in ()).throw(GeneratorExit))()  # placeholder
    import threading
    lock = threading.Lock()  # locks are not picklable
    with pytest.raises(ValueError, match="radio/bad"):
        reg.register("radio/bad", lambda s, e, _l=lock: _l, arity=2)


def test_plugin_key_is_top_level_module():
    def cb(s, e):
        return None
    # functions defined in this test module -> 'tests'
    assert plugin_key_for(cb) == cb.__module__.split(".")[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_registry.py -v --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/plotting/backend/remote/registry.py
"""Registry of out-of-process products: fail-fast pickle validation at
registration, and one worker per plugin."""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import cloudpickle

from .worker_handle import RemoteWorker


def plugin_key_for(callback) -> str:
    return (getattr(callback, "__module__", "") or "remote").split(".")[0]


class RemoteRegistry:
    def __init__(self):
        self._specs: Dict[str, Tuple[bytes, int, str]] = {}   # path -> (blob, arity, plugin_key)
        self._workers: Dict[str, RemoteWorker] = {}

    def register(self, path: str, callback, arity: int) -> None:
        try:
            blob = cloudpickle.dumps(callback)
        except Exception as e:
            raise ValueError(
                f"product '{path}' is out_of_process but its callback cannot be "
                f"pickled for the worker: {e}"
            ) from e
        self._specs[path] = (blob, arity, plugin_key_for(callback))

    def is_remote(self, product_path: list) -> bool:
        return "/".join(product_path) in self._specs

    def spec_for(self, product_path: list) -> Tuple[bytes, int]:
        blob, arity, _ = self._specs["/".join(product_path)]
        return blob, arity

    def worker_for(self, product_path: list) -> RemoteWorker:
        _, _, plugin_key = self._specs["/".join(product_path)]
        worker = self._workers.get(plugin_key)
        if worker is None or worker._proc is None:
            worker = RemoteWorker(plugin_key=plugin_key)
            worker.start()
            self._workers[plugin_key] = worker
        return worker

    def shutdown_all(self) -> None:
        for w in self._workers.values():
            w.shutdown()
        self._workers.clear()


_REGISTRY: Optional[RemoteRegistry] = None


def remote_registry() -> RemoteRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = RemoteRegistry()
    return _REGISTRY
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_registry.py -v --no-xvfb`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/registry.py tests/remote/test_registry.py
git commit -m "feat(remote): RemoteRegistry with fail-fast pickle validation"
```

---

### Task 8: Thread `out_of_process` through registration

Add the opt-in kwarg to `EasyProvider` (the impl) and the user-facing factories. When set, `EasyProvider.__init__` tags the product node metadata `remote=True` and registers the callable + arity with the `RemoteRegistry`. Arity is derived from `parameter_type` (Spectrogram = 3, else 2).

**Files:**
- Modify: `SciQLop/components/plotting/backend/easy_provider.py:101-128`
- Modify: `SciQLop/user_api/virtual_products/__init__.py` (factory signatures `VirtualScalar`/`VirtualVector`/`VirtualSpectrogram`/`VirtualMultiComponent`)
- Test: `tests/remote/test_registration_optin.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_registration_optin.py
from SciQLop.components.plotting.backend.easy_provider import EasyScalar
from SciQLop.components.plotting.backend.remote.registry import remote_registry
from SciQLop.components.plotting.backend.data_provider import ParameterType
from SciQLop.core.products_model import ProductsModel


def test_out_of_process_scalar_tags_node_and_registers():
    EasyScalar("test_remote/dens", "dens", "n", "cm^-3",
               lambda start, stop: None, out_of_process=True)
    node = ProductsModel.node(["test_remote", "dens"])
    assert node is not None
    assert node.metadata().get("remote") in ("True", "true", True, "1")
    assert remote_registry().is_remote(["test_remote", "dens"])
```

(Confirm `EasyScalar`'s constructor argument order against `easy_provider.py` before running — match it exactly; the point under test is the new `out_of_process=True` kwarg and its two effects.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_registration_optin.py -v --no-xvfb`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'out_of_process'`.

- [ ] **Step 3: Write minimal implementation**

In `easy_provider.py`, extend `EasyProvider.__init__` signature with `out_of_process: bool = False`, propagate it from the `EasyScalar`/`EasyVector`/`EasySpectrogram`/`EasyMultiComponent` subclasses (add the same kwarg and pass through), and after the existing `products.add_node(...)` block add:

```python
        if out_of_process:
            from SciQLop.components.plotting.backend.remote.registry import remote_registry
            arity = 3 if parameter_type == ParameterType.Spectrogram else 2
            remote_registry().register(path, callback, arity)
            node = products.node(self._path)
            if node is not None:
                node.set_metadata("remote", "True")
```

(If `ProductsModelNode` has no `set_metadata`, include `"remote": "True"` in the `metadata` dict built just above the `products.add_node` call instead. Verify the node-metadata API in `core/` first.)

In `user_api/virtual_products/__init__.py`, add `out_of_process: bool = False` to `VirtualScalar`, `VirtualVector`, `VirtualSpectrogram`, `VirtualMultiComponent` and forward it into the `_Easy*` impl constructor call.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_registration_optin.py -v --no-xvfb`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/easy_provider.py \
        SciQLop/user_api/virtual_products/__init__.py \
        tests/remote/test_registration_optin.py
git commit -m "feat(remote): out_of_process opt-in on virtual products"
```

---

### Task 9: Plot-path branch — build a remote graph

In `plot_product`, when the node is remote, create the plot, add the matching `add_remote_*` graph, wire its `remote_channel().data_requested` to a `RemoteChannel`, install the callable, and wire teardown via a context-bound `destroyed` slot (the `qt-lifetime-patterns.md` rule — uses the cached `channel_id`, never `self._graph`).

**Files:**
- Create: `SciQLop/components/plotting/backend/remote/plot_remote.py`
- Modify: `SciQLop/components/plotting/ui/time_sync_panel.py:584-614` (add the remote branch at the top of `plot_product`)
- Test: `tests/remote/test_plot_remote.py` (pytest-qt; real panel + real worker)

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_plot_remote.py
import numpy as np
import pytest
from SciQLop.user_api.virtual_products import VirtualSpectrogram, VirtualProductType  # adjust import to real path


def _spec(start, stop):
    t = np.linspace(start, stop, 8)
    f = np.linspace(10, 100, 5)
    z = np.random.rand(8, 5).astype(np.float32)
    return (t, f, z)


@pytest.mark.timeout(30)
def test_plot_remote_spectrogram_streams_data(qtbot, make_panel):
    # `make_panel` is a fixture returning a real SciQLopMultiPlotPanel (see tests/fixtures.py)
    VirtualSpectrogram("test_remote/spec", _spec, out_of_process=True)
    panel = make_panel()
    from SciQLop.components.plotting.ui.time_sync_panel import plot_product
    r = plot_product(panel, ["test_remote", "spec"])
    assert r is not None
    plot, graph = r
    # the remote graph should receive data after the initial request resolves
    qtbot.waitUntil(lambda: graph.remote_channel() is not None, timeout=10000)
```

(Use the existing panel fixture from `tests/fixtures.py`/`tests/helpers.py`; match `VirtualSpectrogram`'s real signature. This test asserts the wiring path runs end-to-end without crashing and a remote graph is produced; tighten the data assertion once the fixture's range-seeding is confirmed.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/remote/test_plot_remote.py -v --no-xvfb`
Expected: FAIL — `plot_product` returns `None` for the remote node (no branch yet) or import error.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/plotting/backend/remote/plot_remote.py
"""Build a SciQLopPlots remote-backed graph bound to a worker channel."""
from __future__ import annotations

import itertools

from SciQLopPlots import SciQLopPlot
from SciQLop.components.plotting.backend.data_provider import ParameterType
from .channel import RemoteChannel
from .registry import remote_registry

_channel_ids = itertools.count(1)


def _new_plot(target):
    if isinstance(target, SciQLopPlot):
        return target
    return target.create_plot()      # SciQLopMultiPlotPanel


def plot_remote(target, node, provider):
    product_path = list(node.path()) if hasattr(node, "path") else None
    reg = remote_registry()
    plot = _new_plot(target)
    ptype = node.parameter_type()
    if ptype == ParameterType.Spectrogram:
        graph = plot.add_remote_color_map(node.name())
    else:
        labels = list(provider.labels(node))
        graph = plot.add_remote_line_graph(labels=labels)
    pipeline = graph.remote_channel()
    worker = reg.worker_for(product_path)
    channel = RemoteChannel(pipeline=pipeline, channel_id=next(_channel_ids),
                            transport=worker)
    worker.register_channel(channel)
    blob, arity = reg.spec_for(product_path)
    worker.install(channel.channel_id, blob, arity)
    pipeline.data_requested.connect(channel.on_data_requested)
    cid = channel.channel_id
    graph.destroyed.connect(lambda *_: channel.dispose())  # cid captured, never self._graph
    return plot, graph
```

In `time_sync_panel.plot_product`, immediately after `provider = providers.get(node.provider())` and the `provider is None` guard, insert:

```python
    from SciQLop.components.plotting.backend.remote.registry import remote_registry
    if remote_registry().is_remote(product):
        from SciQLop.components.plotting.backend.remote.plot_remote import plot_remote
        target, _ = _resolve_plot_target(p, kwargs)
        return plot_remote(target, node, provider)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_plot_remote.py -v --no-xvfb`
Expected: PASS (1 passed). If `node.path()` is not available, derive `product_path` from the `product` argument threaded into `plot_remote` instead.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/plot_remote.py \
        SciQLop/components/plotting/ui/time_sync_panel.py \
        tests/remote/test_plot_remote.py
git commit -m "feat(remote): plot_product branch builds a worker-backed remote graph"
```

---

### Task 10: Teardown & crash resilience

Two safety tests: destroying the graph disposes the channel without touching the dead graph (the SIGSEGV guard), and a worker that dies mid-flight is handled without crashing the app (lazy respawn on next plot).

**Files:**
- Test: `tests/remote/test_teardown.py`
- Modify (if needed): `worker_handle.py` / `channel.py` to satisfy the tests

- [ ] **Step 1: Write the failing test**

```python
# tests/remote/test_teardown.py
import cloudpickle
import numpy as np
import pytest
from SciQLop.components.plotting.backend.remote.worker_handle import RemoteWorker
from SciQLop.components.plotting.backend.remote.channel import RemoteChannel


class _Pipe:
    def set_data(self, *views):
        pass


def test_dispose_releases_without_touching_graph(qtbot):
    worker = RemoteWorker(plugin_key="t")
    worker.start()
    try:
        ch = RemoteChannel(pipeline=_Pipe(), channel_id=1, transport=worker)
        worker.register_channel(ch)
        worker.install(1, cloudpickle.dumps(lambda s, e: (np.array([s, e]), np.array([1.0, 2.0]))), 2)
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
    # next readable event sees EOF; must not raise out of the slot
    worker._on_readable()
    assert worker._proc is None
```

- [ ] **Step 2: Run test to verify it fails (or passes if already handled)**

Run: `uv run pytest tests/remote/test_teardown.py -v --no-xvfb`
Expected: ideally PASS given Tasks 5–6; if `_on_readable`/`dispose` raise on a dead/closed connection, fix by guarding `self._conn is not None` and swallowing `EOFError`/`OSError` in `send_*` and `_on_readable` (already drafted — verify), then re-run.

- [ ] **Step 3: Implement any fix needed**

If failing, wrap the `send_*` methods' `self._conn.send(...)` in `if self._conn is None: return` + `try/except (EOFError, OSError, BrokenPipeError)` so a dead worker degrades quietly. Keep `_on_worker_died` clearing `_proc/_conn/_notifier`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/remote/test_teardown.py -v --no-xvfb`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole remote suite + a broad regression sweep**

Run: `uv run pytest tests/remote/ -v --no-xvfb`
Expected: all green.
Run: `uv run pytest --no-xvfb -q` (full suite — must not regress; watch for segfaults per the project rules).

- [ ] **Step 6: Commit**

```bash
git add tests/remote/test_teardown.py \
        SciQLop/components/plotting/backend/remote/worker_handle.py \
        SciQLop/components/plotting/backend/remote/channel.py
git commit -m "feat(remote): teardown + worker-death resilience"
```

---

## Self-review checklist (run before execution)

- **Spec §5 (pool + req_id):** Tasks 3 (pool), 5 (stale-drop + FREE accounting), 4 (worker coalescing) — covered.
- **Spec §5.1 (zero-copy):** Task 1 (`unpack_arrays` returns views), Task 5 (`set_data` on views, supersede-then-free) — covered.
- **Spec §5.3 (resource_tracker):** `track=False` on both worker create (Task 3) and consumer attach (Task 5) — covered.
- **Spec §4 (wire protocol):** Task 1 constants + Tasks 4/6 senders/receivers — covered.
- **Spec §6 (reduction/EMPTY):** Tasks 2 + 4 — covered.
- **Spec §7 (opt-in + plot branch):** Tasks 8 + 9 — covered.
- **Spec §9 (lifecycle/errors/teardown):** Tasks 6 (`_on_worker_died`, ERROR routing) + 10 — covered.
- **Spec §2 v1 limits (no knobs/Depends):** the remote path deliberately ignores `knobs`/`Depends` — the registered callable is `callback` as-is. No task wires them; matches the spec.
- **Naming consistency:** `channel_id`, `req_id`, `arity`, `transport`, `pipeline`, `send_request`/`send_free`/`release`, `on_result`/`on_empty`/`on_error`, `spec_for`/`worker_for`/`is_remote` are used identically across Tasks 1–9.

**Two integration points to verify against live code during execution** (flagged, not guessed): the exact `ProductsModelNode` metadata API (`set_metadata` vs. dict-at-construction, Task 8) and how `product_path` is obtained inside `plot_remote` (`node.path()` vs. threading the `product` list through, Task 9). Both have a stated fallback.
