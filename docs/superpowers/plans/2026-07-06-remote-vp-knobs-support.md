# Remote Virtual-Product Knobs Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `out_of_process=True` virtual products support runtime knobs — currently the worker calls the raw callback as `cb(start, stop)` with no knob values, and remote graphs get no knob UI at all.

**Architecture:** Extend the `REQUEST` wire message to carry a `knobs` dict end-to-end (worker → `cb(start, stop, **knobs)`); build a small registration-time wrapper in `EasyProvider` that applies the existing range-conversion + `knobs_model` shaping before handing the callable to the remote registry; generalize the existing local knob-UI attachment so remote graphs get the same on-plot handles + inspector extension, pushing value changes into the channel instead of a local callback attribute.

**Tech Stack:** Python, PySide6/Qt signals, `cloudpickle`, `multiprocessing.connection`, `pytest`/`pytest-qt`.

## Global Constraints

- Design doc: `docs/superpowers/specs/2026-07-06-remote-vp-knobs-support-design.md` (commit `14e19bea`). Every requirement in it must map to a task below.
- Scope is knobs only. `Depends`-based dependencies and `debug=True` stay unsupported for `out_of_process=True` — both must raise `ValueError` at registration, not silently degrade.
- No backwards-compatibility shims for the wire format: main process and worker subprocess are always spawned from the same code (`sys.executable -m ...`), so the `REQUEST` tuple shape can change directly with no version negotiation.
- Run tests with `uv run pytest <path> --no-xvfb` (per project convention — do not run the full suite repeatedly, only the touched files/dirs plus one full run at the end).
- Follow existing code idioms exactly (see file-by-file notes in each task) — do not introduce new patterns where an existing one already fits.

---

## Task 1: Extend the REQUEST wire format to carry knob values

**Files:**
- Modify: `SciQLop/components/plotting/backend/remote/protocol.py:14`
- Modify: `SciQLop/components/plotting/backend/remote/channel.py`
- Modify: `SciQLop/components/plotting/backend/remote/worker_handle.py:100-101`
- Modify: `SciQLop/components/plotting/backend/remote/worker.py`
- Modify: `tests/remote/test_worker.py` (3 existing tests need their raw `REQUEST` tuples updated)
- Modify: `tests/remote/test_channel.py` (`FakeTransport.send_request` signature)
- Test: `tests/remote/test_worker.py`, `tests/remote/test_channel.py` (new tests, listed in steps below)

**Interfaces:**
- Produces: `RemoteChannel.set_knobs(knobs: dict) -> None` — stores the dict, included in every subsequent `send_request` call.
- Produces: wire shape `(P.REQUEST, channel_id, req_id, start, stop, knobs)` where `knobs` is always a `dict` (possibly `{}`).
- Consumes (by Task 3): `RemoteChannel.set_knobs()` and `RemoteChannel.on_data_requested_values(start, stop)` (already exists, unchanged signature).

This task changes both ends of the pipe together (main-process senders and the worker's receiver) because they only work when consistent — it lands as one commit.

Note on spec §7: the spec lists `tests/remote/test_protocol.py` as a place to cover the `knobs` field. `protocol.py` has no logic for the `REQUEST` shape beyond a string constant and a comment — there is nothing to unit-test there in isolation. That coverage is folded into this task's `test_worker.py`/`test_channel.py` tests instead, which exercise the shape where it's actually consumed.

- [ ] **Step 1: Write a pure-function test for knob-aware coalescing**

Add to `tests/remote/test_worker.py`:

```python
def test_coalesce_keeps_latest_knobs_with_latest_request():
    from SciQLop.components.plotting.backend.remote.worker import _coalesce, _WorkerState
    state = _WorkerState()
    msgs = [
        (P.REQUEST, 1, 1, 0.0, 1.0, {"gain": 1.0}),
        (P.REQUEST, 1, 2, 0.0, 2.0, {"gain": 2.0}),
    ]
    latest = _coalesce(msgs, state, conn=None)
    assert latest == {1: (2, 0.0, 2.0, {"gain": 2.0})}
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/remote/test_worker.py::test_coalesce_keeps_latest_knobs_with_latest_request -v --no-xvfb`
Expected: FAIL — `_coalesce`'s current `REQUEST` branch does `_, ch, req, start, stop = m`, which raises `ValueError: too many values to unpack (expected 5)` on the 6-tuple.

- [ ] **Step 3: Update `worker.py` to thread `knobs` through**

In `SciQLop/components/plotting/backend/remote/worker.py`, change the `_coalesce` `REQUEST` branch (currently `elif tag == P.REQUEST: _, ch, req, start, stop = m; latest[ch] = (req, start, stop)`):

```python
        elif tag == P.REQUEST:
            _, ch, req, start, stop, knobs = m
            latest[ch] = (req, start, stop, knobs)
```

Change `_serve_request`'s signature and body (currently ends with `result = cb(start, stop)`):

```python
def _serve_request(conn, state, channel_id, req_id, start, stop, knobs) -> None:
    cb = state.callables.get(channel_id)
    if cb is None:
        return
    try:
        result = cb(start, stop, **knobs)
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
```

Change `serve()`'s dispatch loop (currently `for channel_id, (req_id, start, stop) in latest.items(): _serve_request(conn, state, channel_id, req_id, start, stop)`):

```python
        for channel_id, (req_id, start, stop, knobs) in latest.items():
            _serve_request(conn, state, channel_id, req_id, start, stop, knobs)
```

Update the `protocol.py` comment (line 14) from `# (REQUEST, channel_id, req_id, start, stop)` to:

```python
REQUEST = "REQUEST"      # (REQUEST, channel_id, req_id, start, stop, knobs)
```

- [ ] **Step 4: Run the new test, verify it passes**

Run: `uv run pytest tests/remote/test_worker.py::test_coalesce_keeps_latest_knobs_with_latest_request -v --no-xvfb`
Expected: PASS

- [ ] **Step 5: Fix the 3 existing tests in `test_worker.py` that construct raw 5-tuple REQUESTs**

They now send a shape the worker no longer understands. In `tests/remote/test_worker.py`, change each:

```python
    main.send((P.REQUEST, 1, 1, 0.0, 10.0))
```
to
```python
    main.send((P.REQUEST, 1, 1, 0.0, 10.0, {}))
```

Apply the same `, {}` addition to the other two `main.send((P.REQUEST, ...))` calls (in `test_callback_returning_none_yields_empty` and `test_callback_raising_yields_error_with_traceback`).

- [ ] **Step 6: Write a full pipe+thread test that knobs actually reach the callback**

Add to `tests/remote/test_worker.py` (mirrors the existing `_run_worker` pattern):

```python
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
```

This needs `shared_memory` imported — check the top of the file; it's already imported (`from multiprocessing import shared_memory`).

- [ ] **Step 7: Run the whole file, verify everything passes**

Run: `uv run pytest tests/remote/test_worker.py -v --no-xvfb`
Expected: all PASS (6 tests: 3 pre-existing fixed + 2 new).

- [ ] **Step 8: Update `RemoteChannel` to hold and send knob values**

In `SciQLop/components/plotting/backend/remote/channel.py`, change `__init__` (currently ends `self._held: Optional[shared_memory.SharedMemory] = None; self._held_name: Optional[str] = None`):

```python
    def __init__(self, pipeline, channel_id: int, transport):
        self._pipeline = pipeline
        self.channel_id = channel_id
        self._transport = transport
        self._latest_req_id = 0
        self._held: Optional[shared_memory.SharedMemory] = None
        self._held_name: Optional[str] = None
        self._knobs: dict = {}

    def set_knobs(self, knobs: dict) -> None:
        self._knobs = dict(knobs)
```

Change `on_data_requested_values` (currently `self._transport.send_request(self.channel_id, self._latest_req_id, start, stop)`):

```python
    def on_data_requested_values(self, start: float, stop: float) -> None:
        self._latest_req_id += 1
        self._transport.send_request(self.channel_id, self._latest_req_id, start, stop, self._knobs)
```

- [ ] **Step 9: Update `worker_handle.py`'s `send_request` to forward knobs**

In `SciQLop/components/plotting/backend/remote/worker_handle.py`, change:

```python
    def send_request(self, channel_id: int, req_id: int, start: float, stop: float, knobs: dict) -> None:
        self._send((P.REQUEST, channel_id, req_id, start, stop, knobs))
```

- [ ] **Step 10: Update `FakeTransport` in `test_channel.py` to accept knobs**

In `tests/remote/test_channel.py`, change:

```python
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
```

(Only the `send_request` signature and the appended `knobs` element change — everything else in the file is untouched. Existing assertions like `[r[1] for r in t.requests] == [1, 2]` still work since they index by position, not by tuple length.)

- [ ] **Step 11: Write a new test for `set_knobs` propagation**

Add to `tests/remote/test_channel.py`:

```python
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
```

- [ ] **Step 12: Run the whole file, verify everything passes**

Run: `uv run pytest tests/remote/test_channel.py -v --no-xvfb`
Expected: all PASS (6 tests: 4 pre-existing + 2 new).

- [ ] **Step 13: Regression-check the other files that exercise `send_request` through the real classes end-to-end**

Run: `uv run pytest tests/remote/test_worker_handle.py tests/remote/test_teardown.py tests/remote/test_plot_remote.py tests/remote/test_registration_optin.py -v --no-xvfb`
Expected: all PASS unchanged — none of these construct `REQUEST` tuples directly (they call `RemoteChannel.on_data_requested_values(...)` or go through `plot_product`), so they automatically pick up the new `knobs={}` default with no test-code changes needed. These are the tests most likely to catch a real end-to-end wire mismatch, since they spawn an actual worker subprocess.

- [ ] **Step 14: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/protocol.py \
        SciQLop/components/plotting/backend/remote/channel.py \
        SciQLop/components/plotting/backend/remote/worker_handle.py \
        SciQLop/components/plotting/backend/remote/worker.py \
        tests/remote/test_worker.py tests/remote/test_channel.py
git commit -m "feat(remote): thread knob values through the REQUEST wire message"
```

---

## Task 2: Registration-time remote-callback wrapper + guards in `EasyProvider`

**Files:**
- Modify: `SciQLop/components/plotting/backend/easy_provider.py`
- Test: `tests/test_virtual_products/test_remote_callback_wrapper.py` (new file)
- Test: `tests/remote/test_registration_optin.py` (regression run only, no edits expected)

**Interfaces:**
- Consumes: nothing from Task 1 (this task is independently testable — `_build_remote_callback` is a pure function).
- Produces: `_build_remote_callback(callback, range_stack: list, knobs_model: Optional[type], knobs_kwarg_name: str) -> Callable[..., Any]` — used by Task 1's wire format at runtime (the worker calls the object this returns as `cb(start, stop, **knobs)`), and consumed conceptually by Task 3 (knob specs still come from `provider.get_knobs(node)`, unaffected by this task).
- Produces: `EasyProvider.__init__` raises `ValueError` when `out_of_process=True` is combined with `debug=True` or with a callback carrying any `Depends`-annotated parameter.

- [ ] **Step 1: Write failing tests for `_build_remote_callback`**

Create `tests/test_virtual_products/test_remote_callback_wrapper.py`:

```python
from datetime import datetime, timezone

from pydantic import BaseModel

from SciQLop.components.plotting.backend.easy_provider import (
    _build_remote_callback, _to_datetime,
)


def test_remote_callback_passes_through_plain_kwargs():
    calls = []

    def cb(start, stop, gain=1.0):
        calls.append((start, stop, gain))
        return None

    remote_cb = _build_remote_callback(cb, range_stack=[], knobs_model=None, knobs_kwarg_name="knobs")
    remote_cb(0.0, 10.0, gain=3.0)
    assert calls == [(0.0, 10.0, 3.0)]


def test_remote_callback_defaults_to_empty_knobs():
    calls = []

    def cb(start, stop):
        calls.append((start, stop))
        return None

    remote_cb = _build_remote_callback(cb, range_stack=[], knobs_model=None, knobs_kwarg_name="knobs")
    remote_cb(0.0, 10.0)
    assert calls == [(0.0, 10.0)]


def test_remote_callback_applies_range_stack():
    calls = []

    def cb(start, stop):
        calls.append((start, stop))
        return None

    remote_cb = _build_remote_callback(
        cb, range_stack=[lambda rng: _to_datetime(*rng)],
        knobs_model=None, knobs_kwarg_name="knobs")
    remote_cb(0.0, 10.0)
    assert calls == [(datetime.fromtimestamp(0.0, tz=timezone.utc),
                       datetime.fromtimestamp(10.0, tz=timezone.utc))]


def test_remote_callback_constructs_knobs_model():
    calls = []

    class Knobs(BaseModel):
        gain: float = 1.0

    def cb(start, stop, knobs):
        calls.append((start, stop, knobs))
        return None

    remote_cb = _build_remote_callback(cb, range_stack=[], knobs_model=Knobs, knobs_kwarg_name="knobs")
    remote_cb(0.0, 10.0, gain=5.0)
    assert calls == [(0.0, 10.0, Knobs(gain=5.0))]


def test_remote_callback_preserves_module_and_qualname_for_plugin_key():
    """RemoteRegistry.plugin_key_for() groups workers by callback.__module__ —
    the wrapper must look like the original callback, not like easy_provider,
    or every plugin's out_of_process VPs would collapse onto one worker."""
    def cb(start, stop):
        return None

    remote_cb = _build_remote_callback(cb, range_stack=[], knobs_model=None, knobs_kwarg_name="knobs")
    assert remote_cb.__module__ == cb.__module__
    assert remote_cb.__qualname__ == cb.__qualname__
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/test_virtual_products/test_remote_callback_wrapper.py -v --no-xvfb`
Expected: FAIL — `ImportError: cannot import name '_build_remote_callback'`.

- [ ] **Step 3: Add `_build_remote_callback` to `easy_provider.py`**

Add `import functools` to the top of `SciQLop/components/plotting/backend/easy_provider.py` (alongside the existing `import inspect` / `import warnings`).

Add this function right after `_to_datetime64` (currently the last module-level function before `class EasyProvider`):

```python
def _build_remote_callback(callback: VirtualProductCallback, range_stack: list,
                            knobs_model: Optional[type], knobs_kwarg_name: str) -> Callable:
    """Wrap *callback* for out-of-process execution: apply the same range-type
    conversion and knobs_model shaping that EasyProvider._invoke_callback does
    in-process, so the worker only ever needs to call cb(start, stop, **knobs).

    functools.wraps preserves __module__/__qualname__ so RemoteRegistry's
    plugin_key_for() still groups this product's worker with the rest of its
    plugin instead of with easy_provider itself.
    """
    @functools.wraps(callback)
    def _remote_call(start: float, stop: float, **knobs):
        rng = (start, stop)
        for fn in range_stack:
            rng = fn(rng)
        if knobs_model is not None:
            kwargs = {knobs_kwarg_name: knobs_model(**knobs)}
        else:
            kwargs = dict(knobs)
        return callback(*rng, **kwargs)
    return _remote_call
```

- [ ] **Step 4: Run the test file, verify it passes**

Run: `uv run pytest tests/test_virtual_products/test_remote_callback_wrapper.py -v --no-xvfb`
Expected: all 5 PASS.

- [ ] **Step 5: Write failing tests for the two registration guards**

Append to `tests/test_virtual_products/test_remote_callback_wrapper.py`:

```python
import pytest
from typing import Annotated

from speasy.products import SpeasyVariable

from SciQLop.components.plotting.backend.dependencies import Depends


def test_out_of_process_with_debug_raises(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar

    with pytest.raises(ValueError, match="debug"):
        EasyScalar(path="test_remote_guard/debug", get_data_callback=lambda s, e: None,
                   component_name="x", metadata={}, out_of_process=True, debug=True)


def test_out_of_process_with_dependency_raises(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar

    def cb(start: float, stop: float,
           dep: Annotated[SpeasyVariable, Depends("speasy//amda//imf")] = None):
        return None

    with pytest.raises(ValueError, match="Depends"):
        EasyScalar(path="test_remote_guard/dep", get_data_callback=cb,
                   component_name="x", metadata={}, out_of_process=True)


def test_out_of_process_without_debug_or_deps_still_registers(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.backend.remote.registry import remote_registry
    import SciQLop.components.plotting.backend.remote.registry as reg_mod

    old = reg_mod._REGISTRY
    reg_mod._REGISTRY = None
    try:
        EasyScalar(path="test_remote_guard/ok", get_data_callback=lambda s, e: None,
                   component_name="x", metadata={}, out_of_process=True)
        assert remote_registry().is_remote(["test_remote_guard", "ok"])
    finally:
        if reg_mod._REGISTRY is not None:
            reg_mod._REGISTRY.shutdown_all()
        reg_mod._REGISTRY = old
```

- [ ] **Step 6: Run it, verify the two guard tests fail**

Run: `uv run pytest tests/test_virtual_products/test_remote_callback_wrapper.py -v --no-xvfb`
Expected: `test_out_of_process_with_debug_raises` and `test_out_of_process_with_dependency_raises` FAIL with `Failed: DID NOT RAISE <class 'ValueError'>`. The third new test should already PASS (nothing to guard against yet).

- [ ] **Step 7: Reorder `EasyProvider.__init__` and add the guards + wrapper registration**

In `SciQLop/components/plotting/backend/easy_provider.py`, `EasyProvider.__init__` currently reads (lines ~108-151):

```python
        super(EasyProvider, self).__init__(name=make_simple_incr_name(_name_callable(callback)), data_order=data_order,
                                           cacheable=cacheable)
        self._path = path.split('/')
        product_name = self._path[-1]
        product_path = self._path[:-1]
        metadata = {
            **metadata,
            "description": f"Virtual {parameter_type.name} product built from Python function: {self.name}",
            "stable_id": path,
            **({"remote": "True"} if out_of_process else {}),
        }
        products.add_node(
            product_path,
            ProductsModelNode(product_name, self.name, metadata, ProductsModelNodeType.PARAMETER, parameter_type, "",
                              None)
        )
        if out_of_process:
            from SciQLop.components.plotting.backend.remote.registry import remote_registry
            arity = 3 if parameter_type == ParameterType.Spectrogram else 2
            remote_registry().register(path, callback, arity)
        self._callback = callback
        self._parameter_type = parameter_type
        self._debug = debug
        self._knobs_model = knobs_model
        self._knobs_kwarg_name = knobs_kwarg_name
        self._knob_specs = self._compute_knob_specs(callback, knobs_model)
        self._dependency_specs = extract_dependencies_from_callback(callback)

        stack = []
        arguments_type = _arguments_type(callback)
        match arguments_type:
            case ArgumentsType.Datetime:
                stack.append(lambda rng: _to_datetime(*rng))
            case ArgumentsType.Datetime64:
                stack.append(lambda rng: _to_datetime64(*rng))
            case ArgumentsType.Float:
                pass
            case ArgumentsType.Unknown:
                warnings.warn(f"""Can't determine arguments type for {self.name}, missing type hints, assuming float by default.
Please add type hints to the callback function to avoid this warning:
def {self.name}(start: float, stop: float) -> Optional[SpeasyVariable]:
    ...
            """)
        self._range_stack = stack
```

Replace it with (the `out_of_process` block moves from right after `products.add_node(...)` to after `self._range_stack = stack`, so it can use `self._dependency_specs` and `self._range_stack`):

```python
        super(EasyProvider, self).__init__(name=make_simple_incr_name(_name_callable(callback)), data_order=data_order,
                                           cacheable=cacheable)
        self._path = path.split('/')
        product_name = self._path[-1]
        product_path = self._path[:-1]
        metadata = {
            **metadata,
            "description": f"Virtual {parameter_type.name} product built from Python function: {self.name}",
            "stable_id": path,
            **({"remote": "True"} if out_of_process else {}),
        }
        products.add_node(
            product_path,
            ProductsModelNode(product_name, self.name, metadata, ProductsModelNodeType.PARAMETER, parameter_type, "",
                              None)
        )
        self._callback = callback
        self._parameter_type = parameter_type
        self._debug = debug
        self._knobs_model = knobs_model
        self._knobs_kwarg_name = knobs_kwarg_name
        self._knob_specs = self._compute_knob_specs(callback, knobs_model)
        self._dependency_specs = extract_dependencies_from_callback(callback)

        stack = []
        arguments_type = _arguments_type(callback)
        match arguments_type:
            case ArgumentsType.Datetime:
                stack.append(lambda rng: _to_datetime(*rng))
            case ArgumentsType.Datetime64:
                stack.append(lambda rng: _to_datetime64(*rng))
            case ArgumentsType.Float:
                pass
            case ArgumentsType.Unknown:
                warnings.warn(f"""Can't determine arguments type for {self.name}, missing type hints, assuming float by default.
Please add type hints to the callback function to avoid this warning:
def {self.name}(start: float, stop: float) -> Optional[SpeasyVariable]:
    ...
            """)
        self._range_stack = stack

        if out_of_process:
            if debug:
                raise ValueError(
                    f"virtual product '{path}': out_of_process=True is incompatible with "
                    f"debug=True (debug diagnostics require the callback to run in-process)")
            if self._dependency_specs:
                dep_names = [s.name for s in self._dependency_specs]
                raise ValueError(
                    f"virtual product '{path}': out_of_process=True does not support "
                    f"Depends() dependencies (found on parameter(s) {dep_names}); "
                    f"resolve dependencies in-process or drop out_of_process")
            from SciQLop.components.plotting.backend.remote.registry import remote_registry
            remote_callback = _build_remote_callback(
                callback, self._range_stack, knobs_model, knobs_kwarg_name)
            arity = 3 if parameter_type == ParameterType.Spectrogram else 2
            remote_registry().register(path, remote_callback, arity)
```

- [ ] **Step 8: Run the test file, verify everything passes**

Run: `uv run pytest tests/test_virtual_products/test_remote_callback_wrapper.py -v --no-xvfb`
Expected: all 8 PASS.

- [ ] **Step 9: Regression-check existing out_of_process and knobs tests**

Run: `uv run pytest tests/remote/test_registration_optin.py tests/remote/test_plot_remote.py tests/test_virtual_products/test_knobs_easy_provider.py tests/test_plotting/test_plot_product_knobs.py -v --no-xvfb`
Expected: all PASS unchanged — `is_remote()` only checks path presence (unaffected by wrapping the callback), `test_plot_remote.py`'s assertions only check `graph.remote_channel() is not None` (unaffected by which callable backs the worker), and none of these tests touch `out_of_process` + `debug`/`Depends` together.

- [ ] **Step 10: Commit**

```bash
git add SciQLop/components/plotting/backend/easy_provider.py \
        tests/test_virtual_products/test_remote_callback_wrapper.py
git commit -m "feat(vp): shape knobs/range for out_of_process callbacks at registration"
```

---

## Task 3: Knob UI wiring for remote graphs

**Files:**
- Modify: `SciQLop/components/plotting/backend/remote/plot_remote.py`
- Modify: `SciQLop/components/plotting/ui/time_sync_panel.py`
- Test: `tests/test_plotting/test_plot_product_knobs.py` (new tests appended)
- Test: `tests/remote/test_registration_optin.py` (new integration test appended)

**Interfaces:**
- Consumes: `RemoteChannel.set_knobs(dict) -> None` (Task 1); `provider.get_knobs(node) -> list[KnobSpec]` (existing, unaffected by Task 2).
- Produces: `graph._remote_channel` attribute set by `plot_remote()`.
- Produces: `_attach_remote_knob_state(provider, node, channel, r, target=None) -> None` in `time_sync_panel.py`.
- Produces: `_trigger_remote_refetch(graph) -> None` in `time_sync_panel.py`.

- [ ] **Step 1: Write a failing unit test for `_attach_remote_knob_state`**

Append to `tests/test_plotting/test_plot_product_knobs.py`:

```python
class _FakeRemoteChannel:
    def __init__(self):
        self.knobs_calls = []

    def set_knobs(self, knobs):
        self.knobs_calls.append(dict(knobs))

    def on_data_requested_values(self, start, stop):
        pass


def test_attach_remote_knob_state_binds_channel(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import _attach_remote_knob_state
    from PySide6.QtCore import QObject

    def f(start: float, stop: float,
          gain: Annotated[float, Knob(min=0.0, max=10.0)] = 1.0):
        return np.linspace(start, stop, 4), np.zeros(4)

    provider = EasyScalar(path="vp/remoteknobtest", get_data_callback=f, component_name="x", metadata={})
    graph = QObject()
    channel = _FakeRemoteChannel()

    _attach_remote_knob_state(provider, "vp/remoteknobtest", channel, graph)

    state = graph._knob_state
    assert state.values == {"gain": 1.0}
    assert channel.knobs_calls == [{"gain": 1.0}]   # initial bind

    state.set_value("gain", 5.0)
    assert channel.knobs_calls[-1] == {"gain": 5.0}


def test_attach_remote_knob_state_no_op_for_no_knobs(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import _attach_remote_knob_state
    from PySide6.QtCore import QObject

    def f(start: float, stop: float):
        return np.linspace(start, stop, 4), np.zeros(4)

    provider = EasyScalar(path="vp/remotenoknobs", get_data_callback=f, component_name="x", metadata={})
    graph = QObject()
    channel = _FakeRemoteChannel()

    _attach_remote_knob_state(provider, "vp/remotenoknobs", channel, graph)

    assert not hasattr(graph, "_knob_state")
    assert channel.knobs_calls == []
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/test_plotting/test_plot_product_knobs.py -v --no-xvfb -k remote`
Expected: FAIL — `ImportError: cannot import name '_attach_remote_knob_state'`.

- [ ] **Step 3: Stash the channel on the graph in `plot_remote()`**

In `SciQLop/components/plotting/backend/remote/plot_remote.py`, change:

```python
    channel = RemoteChannel(pipeline=pipeline, channel_id=next(_channel_ids),
                            transport=worker)
    graph._remote_channel = channel
    worker.register_channel(channel)
```

(single line added — `graph._remote_channel = channel` right after `channel` is constructed, matching the existing idiom of stashing state on `graph` used elsewhere for knobs, e.g. `graph._knob_state`.)

- [ ] **Step 4: Add `_trigger_remote_refetch` and `_attach_remote_knob_state` to `time_sync_panel.py`**

In `SciQLop/components/plotting/ui/time_sync_panel.py`, add right after the existing `_trigger_refetch` function (after line 369, before `def _attach_knob_state`):

```python
def _trigger_remote_refetch_impl(graph):
    channel = getattr(graph, "_remote_channel", None)
    if channel is None:
        log.debug("graph has no remote channel — cannot refetch on knob change")
        return
    try:
        current_range = graph.x_axis().range()
        channel.on_data_requested_values(current_range.start(), current_range.stop())
    except Exception:
        log.debug("could not trigger remote refetch for knob change", exc_info=True)


def _trigger_remote_refetch(graph):
    from SciQLop.user_api.threading import on_main_thread
    on_main_thread(_trigger_remote_refetch_impl)(graph)
```

Add this new function right after the existing `_attach_knob_state` function (after its closing line, before `def _dispose_graph_knobs`):

```python
def _attach_remote_knob_state(provider, node, channel, r, target=None):
    """Twin of _attach_knob_state for remote (out_of_process) graphs.

    Duplicated rather than parameterizing _attach_knob_state: the two differ
    in how a value change reaches the data source (callback.knob_state
    assignment vs. channel.set_knobs push) and how refetch is triggered
    (graph.call vs. channel.on_data_requested_values) enough that threading
    both shapes through one function reads worse than two small twins, and
    _attach_knob_state already has direct test coverage on its exact
    (provider, node, callback, r, target) signature that would otherwise need
    updating for no behavioral reason.
    """
    specs = []
    try:
        specs = provider.get_knobs(node)
    except Exception:
        log.error("get_knobs failed for %s", node, exc_info=True)
    if not specs:
        return
    from SciQLop.components.plotting.backend.graph_knobs import GraphKnobState
    from SciQLop.components.plotting.ui.knob_inspector import KnobInspectorExtension
    from SciQLop.components.plotting.ui.knob_inspector.plot_items import create_plot_items
    graph = _graph_from_result(r)
    plot = _plot_from_result(r, target)
    state = GraphKnobState(specs, parent=graph)
    graph._knob_state = state
    channel.set_knobs(state.values)
    state.knobs_changed.connect(lambda values: channel.set_knobs(values))
    refetch_slot = lambda *_: _trigger_remote_refetch(graph)
    graph._knobs_slot = refetch_slot
    state.knobs_changed.connect(refetch_slot)
    state.knobs_changed.connect(
        lambda values, g=graph: update_knobs(g, dict(values))
    )
    graph._visual_knob_dispose = None
    if plot is not None:
        graph._visual_knob_dispose = create_plot_items(plot, state)
    if hasattr(graph, "add_inspector_extension"):
        ext = KnobInspectorExtension(state, parent=graph)
        graph._knob_inspector_ext = ext
        graph.add_inspector_extension(ext)
        ext.destroyed.connect(lambda *_: _dispose_graph_knobs(graph))
```

- [ ] **Step 5: Run the unit tests, verify they pass**

Run: `uv run pytest tests/test_plotting/test_plot_product_knobs.py -v --no-xvfb -k remote`
Expected: both new tests PASS.

- [ ] **Step 6: Wire `_attach_remote_knob_state` into `plot_product`'s remote branch**

In `SciQLop/components/plotting/ui/time_sync_panel.py`, `plot_product` currently has:

```python
    from SciQLop.components.plotting.backend.remote.registry import remote_registry
    if remote_registry().is_remote(product):
        from SciQLop.components.plotting.backend.remote.plot_remote import plot_remote
        target, _ = _resolve_plot_target(p, kwargs)
        return plot_remote(target, node, provider, product)
```

Change it to:

```python
    from SciQLop.components.plotting.backend.remote.registry import remote_registry
    if remote_registry().is_remote(product):
        from SciQLop.components.plotting.backend.remote.plot_remote import plot_remote
        target, _ = _resolve_plot_target(p, kwargs)
        r = plot_remote(target, node, provider, product)
        graph = _graph_from_result(r)
        channel = getattr(graph, "_remote_channel", None) if graph is not None else None
        if channel is not None:
            _attach_remote_knob_state(provider, node, channel, r, target)
        return r
```

- [ ] **Step 7: Write an integration test through `plot_product`**

Append to `tests/remote/test_registration_optin.py`:

```python
def test_out_of_process_scalar_with_knobs_gets_knob_state(qtbot, main_window):
    from typing import Annotated
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import plot_product
    from SciQLop.user_api.knobs import Knob
    from SciQLop.user_api.plot import create_plot_panel

    def f(start: float, stop: float,
          gain: Annotated[float, Knob(min=0.0, max=10.0)] = 2.0):
        import numpy as np
        return np.linspace(start, stop, 4), np.zeros(4)

    EasyScalar(
        path="test_remote_knobs/dens",
        get_data_callback=f,
        component_name="dens",
        metadata={},
        out_of_process=True,
    )

    panel = create_plot_panel()
    result = plot_product(panel._impl, ["test_remote_knobs", "dens"])

    assert result is not None
    plot, graph = result
    assert graph._remote_channel is not None
    assert graph._knob_state.values == {"gain": 2.0}

    qtbot.wait(500)
```

(This mirrors the existing `test_plot_product_remote_scalar_builds_remote_graph` in the same file — same fixtures, same `_isolate_registry` autouse fixture already present at the top of `test_registration_optin.py`.)

- [ ] **Step 8: Run it, verify it passes**

Run: `uv run pytest tests/remote/test_registration_optin.py -v --no-xvfb`
Expected: all PASS, including the new test.

- [ ] **Step 9: Full regression run of every file touched across all three tasks**

Run: `uv run pytest tests/remote/ tests/test_plotting/test_plot_product_knobs.py tests/test_virtual_products/test_remote_callback_wrapper.py tests/test_virtual_products/test_knobs_easy_provider.py -v --no-xvfb`
Expected: all PASS.

- [ ] **Step 10: Full suite run**

Run: `uv run pytest --no-xvfb`
Expected: full pass count reported, exit code 0. Read the actual pass/fail count — do not infer success from a partial grep (per project workflow rules).

- [ ] **Step 11: Commit**

```bash
git add SciQLop/components/plotting/backend/remote/plot_remote.py \
        SciQLop/components/plotting/ui/time_sync_panel.py \
        tests/test_plotting/test_plot_product_knobs.py \
        tests/remote/test_registration_optin.py
git commit -m "feat(plotting): wire knob UI onto remote (out_of_process) graphs"
```
