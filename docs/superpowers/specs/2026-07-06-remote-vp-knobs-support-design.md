# Remote Virtual-Product Knobs Support — Design

**Date:** 2026-07-06
**Status:** Approved design, pending implementation plan
**Depends on:** `SciQLop/components/plotting/backend/remote/` (shipped, see
`2026-06-21-remote-data-source-ipc-design.md`)
**Motivating case:** `sciqlop_radio`'s LOFAR virtual product (external repo,
`plugins_sciqlop/sciqlop_radio`) has interactive `beam`/`sap` knobs that must
keep working if the product is migrated to `out_of_process=True`.

## 1. Problem

`2026-06-21-remote-data-source-ipc-design.md` shipped `out_of_process=True` for
`EasyProvider`-based virtual products, but explicitly deferred knobs as a v1
limitation: the out-of-process path (`plot_remote()` → worker) calls the raw
cloudpickled callback as `cb(start, stop)` — two positional floats, nothing
else. It completely bypasses `EasyProvider._invoke_callback`, which normally
handles knob injection, `Depends` resolution, debug validation, and
float→datetime/datetime64 range conversion.

Concretely: a remote product with `Annotated[int, Knob(...)]` parameters that
have defaults silently always runs with those defaults — SciQLop never
errors, the knob UI (if it existed) would just have no effect. In fact today
remote graphs get **no knobs UI at all**: `plot_product()` branches to
`plot_remote()` before the local path's `_attach_knob_state()` call, so
nothing is wired up.

## 2. Scope

**In scope:** runtime knobs (per-kwarg `Annotated[T, Knob(...)]` params, and
the `knobs_model` Pydantic-model form) for `out_of_process=True` products —
both the wire protocol to carry live values to the worker, and the on-plot
knob UI (draggable handles + inspector "Parameters" extension) that remote
graphs currently lack entirely.

**Explicitly out of scope (v1):**
- **`Depends`-based VP dependencies remotely.** Dependency resolution needs
  the main process's whole product registry (other providers/VPs), which the
  isolated worker doesn't have. `out_of_process=True` on a callback with any
  `Depends`-annotated parameter now raises `ValueError` at registration —
  fail loud rather than silently never resolving it.
- **`debug=True` remotely.** The debug path's diagnostics assume the calling
  process's logger; a worker subprocess has no such plumbing today.
  `out_of_process=True` + `debug=True` raises `ValueError` at registration.

Both guards live in `EasyProvider.__init__` and only fire when
`out_of_process=True` — the existing in-process behavior for both features is
untouched.

## 3. Wire protocol changes

`protocol.py`'s `REQUEST` gains one field, always present:

```
REQUEST = "REQUEST"   # (REQUEST, channel_id, req_id, start, stop, knobs)
```

`knobs` is a plain `dict` of already-coerced primitive values (`{}` for
knob-less products — uniform shape, no optional field, no version
negotiation needed).

- `RemoteChannel` (`remote/channel.py`) gains `_knobs: dict = {}` and
  `set_knobs(values: dict) -> None`; `send_request` / `on_data_requested_values`
  include `self._knobs` in every outgoing `REQUEST`.
- `worker_handle.py`'s `send_request(channel_id, req_id, start, stop)` gains a
  `knobs` parameter, forwarded verbatim into the pipe tuple.
- `worker.py`: `_coalesce`'s `REQUEST` branch unpacks the extra field
  (`latest[ch] = (req, start, stop, knobs)`); `_serve_request` calls
  `cb(start, stop, **knobs)`.

Because the worker already keeps only the **latest** `REQUEST` per channel
when draining its queue, a knob change riding in on the next request is
naturally coalesced with any in-flight pan/zoom — no separate
synchronization message, no ordering invariant to maintain.

**Immediate refetch on knob change** (parity with the local path's
`_trigger_refetch`, which calls `graph.call(current_range)`): read
`graph.x_axis().range()` and call `channel.on_data_requested_values(rng.start(),
rng.stop())` directly. `RemoteChannel` already exposes that method — no new
C++-side hook needed.

## 4. Registration-time wrapper

Today, `out_of_process=True` registers the **raw user callback**:

```python
remote_registry().register(path, callback, arity)   # easy_provider.py:127
```

That's why nothing shapes the call remotely. Fix: build a small wrapper at
registration time and register that instead — a module-level factory in
`easy_provider.py` (generic, not radio-specific):

```python
def _build_remote_callback(callback, range_stack, knobs_model, knobs_kwarg_name):
    def _remote_call(start, stop, **knobs):
        rng = (start, stop)
        for fn in range_stack:
            rng = fn(rng)
        kwargs = {knobs_kwarg_name: knobs_model(**knobs)} if knobs_model is not None else dict(knobs)
        return callback(*rng, **kwargs)
    return _remote_call
```

`range_stack` is exactly the `self._range_stack` already computed in
`EasyProvider.__init__` for the local path (float/datetime/datetime64
conversion) — no new conversion logic, just relocating what
`_invoke_callback` already does into something callable with plain
`(start, stop, **knobs)` and therefore cloudpickle-safe (empirically verified
in the scoping session: closures over module-level helpers, dataclasses, and
`Path`/model objects all pickle cleanly with `cloudpickle.dumps`).

Knob **spec discovery** (`_compute_knob_specs`, used to build the UI) is
unaffected — it already introspects the raw `callback` before wrapping, so
the spec list seen by the UI is identical whether or not the product ends up
wrapped for remote execution.

**Validation guards**, added to `EasyProvider.__init__`, only when
`out_of_process=True`:
- `debug=True` → raise `ValueError`.
- `extract_dependencies_from_callback(callback)` non-empty → raise `ValueError`.

Both run at VP-registration time (main process, during plugin `load()`), so a
misconfigured product fails immediately with a clear message rather than
misbehaving on first data request.

## 5. Knob UI wiring for remote graphs

`_attach_knob_state()` (`time_sync_panel.py`) already does everything that's
identical between local and remote: look up `provider.get_knobs(node)`,
build a `GraphKnobState`, create the on-plot draggable knob handles
(`create_plot_items`), wire the `KnobInspectorExtension` and its disposal.
The only two things that differ are (a) how a knob-value change reaches the
data-fetch path, and (b) how an immediate refetch is triggered. Both become
small parameters supplied by the caller instead of being hardcoded to the
local shape, so the ~30 lines of shared setup are not duplicated:

| | Local (existing) | Remote (new) |
|---|---|---|
| Value sink | `callback.knob_state = state` | `channel.set_knobs(values)` |
| Refetch trigger | `graph.call(current_range)` | `channel.on_data_requested_values(rng.start(), rng.stop())` |

`plot_product()` calls this generalized attachment after `plot_remote()`
returns, same as it does today for the local path. To get from
`plot_remote()`'s return value to the `channel` object at that call site,
`plot_remote()` stashes it as `graph._remote_channel = channel` — matching
the existing idiom already used for knob state (`graph._knob_state`,
`graph._knobs_slot`) rather than changing `plot_remote`'s return signature.

## 6. Error handling

No new error-handling code needed. A bad knob value that makes
`knobs_model(**knobs)` raise, or that makes `callback(...)` raise for any
other reason, is already caught by `_serve_request`'s existing `try/except`
in `worker.py` and surfaces through the existing `ERROR` →
`RemoteChannel.on_error` → `log.error(...)` path.

## 7. Testing

- `tests/remote/test_protocol.py` — `REQUEST` carries a `knobs` dict; `{}`
  for knob-less products.
- `tests/remote/test_worker.py` — `_coalesce` / `_serve_request` forward
  `knobs` into `cb(start, stop, **knobs)`; latest-wins coalescing carries the
  latest knobs along with the latest range.
- `tests/remote/test_channel.py` — `set_knobs()` + `on_data_requested_values()`
  include the stored knobs in the sent request.
- New unit tests for `_build_remote_callback()` in isolation (pure function,
  no subprocess needed): range-stack conversion applied correctly,
  `knobs_model` construction vs. raw-kwargs passthrough, empty-knobs case.
- `EasyProvider` registration tests: `debug=True` + `out_of_process=True`
  raises; a `Depends`-annotated callback + `out_of_process=True` raises.
- Extend `tests/remote/test_plot_remote.py` (or a new UI-level test): a
  remote graph gets a `GraphKnobState` + inspector extension, and a simulated
  knob change results in `channel.set_knobs()` being called and a new
  `REQUEST` sent with the updated values.

## 8. Non-goals / explicit follow-ups

- `Depends` support remotely — needs a design for how (or whether) dependency
  resolution can run inside an isolated worker; tracked as a future item, not
  blocking this one.
- Debug-mode diagnostics remotely — would need log-forwarding from the worker
  subprocess back to SciQLop's log widget; not attempted here.
- This design does not change worker concurrency (`plugin_key_for()` still
  groups all of a plugin's VPs onto one worker subprocess) — out of scope,
  tracked separately in the radio-migration backlog item.
