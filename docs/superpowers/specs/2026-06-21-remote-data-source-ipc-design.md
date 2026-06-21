# Remote Data Source IPC — Design

**Date:** 2026-06-21
**Status:** Approved design, pending implementation plan
**Depends on:** `SciQLopPlots >= 0.29.0` (remote channel API, PR #89)
**Companion:** `SciQLopPlots/docs/remote-channels-sciqlop-handover.md`

## 1. Problem

A slow, pure-Python data source driven by the classic `plot(callback)` path runs
its callback on a **SciQLopPlots worker thread**, holding the GIL for the whole
compute and starving the rest of the app. The motivating case is the
`sciqlop_radio` plugin: its spectrogram callback does `Fido.search` →
`Fido.fetch` → FITS parse → concat, synchronously, for seconds at a time.

SciQLopPlots already ships the **transport-agnostic remote channel** (v0.29.0):
a remote-backed graph emits `data_requested(range)` on pan and accepts finished
buffers back via `set_data`, zero-copy over any buffer-protocol object. **The IPC
layer that drives it is unwritten — this is that layer.**

## 2. Scope

The unit moved out of process is the **data source** — the
`(start, stop) -> data` callable — **not** the plugin. The plugin's UI,
registration, product tree and settings stay in-process; only the heavy compute
escapes the GIL. This maps onto the handover's "Channel = one per product/graph"
model.

**Transport decision: cloudpickle the existing callable (approach A).** The thing
shipped across the boundary *is* the data-source callable, matching the scope
literally and imposing minimal author burden. The radio callback runs nearly
as-is once its compute code is Qt-free (see §8).

### v1 limitations (explicit)

- Remote products support **neither runtime knobs nor `Depends`** — the callable
  is captured at registration. Radio's `continuous.py` callback uses plain
  `(start, stop)` with neither, so it fits v1. Knobs/`Depends` are a documented
  follow-up.
- The worker is **single-threaded**; cross-product parallelism = more worker
  processes (the author's lever, per the handover).

## 3. Components

New component `SciQLop/components/plotting/backend/remote/`:

| Object | Process | Owns | Lifetime |
|---|---|---|---|
| `RemoteRegistry` | main | remote-product table; cloudpickle fail-fast validation at registration | app-global singleton |
| `RemoteWorker` | main | the subprocess + duplex control pipe + `QSocketNotifier` on the pipe fd + `channel_id → RemoteChannel` routing | one per plugin; spawned lazily on first remote plot |
| `RemoteChannel` | main | the SciQLopPlots `remote_channel()`, `channel_id`, `latest_req_id`, consumer-side shm view + `held` segment | one per graph |
| `_worker.py` | worker | unpickled callables keyed by `channel_id`, the shm **pool** (sole creator/unlinker), serial compute loop | the process |

- Worker launched via `multiprocessing` **spawn** using `sys.executable` (the
  workspace venv) → identical deps, **no inherited Qt/fork state**.
- Main side runs **no background threads** — the `QSocketNotifier` fires replies
  straight onto the main thread, where `set_data` is required to be anyway. Sends
  (`REQUEST`/`FREE`) also originate on the main thread (`data_requested` fires
  there).

## 4. Wire protocol

Small pickled tuples over a `multiprocessing` duplex pipe. Bulk data travels
through shared memory; the pipe carries only handles + metadata.

```
main → worker:  INSTALL(channel_id, cloudpickled_callable)
                REQUEST(channel_id, req_id, start, stop)
                FREE(channel_id, shm_name)          # "you may reuse this segment"
                RELEASE(channel_id) / SHUTDOWN
worker → main:  RESULT(channel_id, req_id, shm_name, [(shape, dtype, offset)...], arity)
                EMPTY(channel_id, req_id)           # callback returned None — no shm
                ERROR(channel_id, req_id, traceback_str)
```

## 5. The zero-copy shm pool + `req_id` protocol (core)

### 5.1 Zero-copy

The boundary crossing is genuinely zero-copy: the worker writes result bytes once
into a shm segment; the main process wraps it (`np.ndarray(shape, dtype,
buffer=shm.buf)`) and hands it to `ch.set_data(...)`, which SciQLopPlots reads in
place (handover §3.3). The big `z` spectrogram array never gets copied on the
main side.

The **one** unavoidable copy is in the worker: third-party libs allocate the
result in private heap, so `shm_view[:] = result` is a single local `memcpy` —
negligible (single-digit MB) against the seconds of Fido fetch/parse. Dtypes are
kept native (`z` stays float32) so there is no conversion copy; `set_data`
dispatches on dtype.

### 5.2 The race-free reuse rule

A blind ring (`segment = k % N`) is **unsafe**: with a slow consumer the worker
can overwrite a segment SciQLopPlots is still rendering → torn read → crash.
Therefore reuse is **consumer-driven, never time-driven**. A segment handed out
is "out" until the main side explicitly returns it with `FREE`.

- **Worker, on REQUEST:** take a reusable segment ≥ needed bytes (else
  allocate/grow); mark it *out*; write arrays; reply `RESULT`. **Never touch an
  *out* segment.**
- **Main, on RESULT:**
  - **stale** (`req_id < latest_req_id`): close view, immediately `FREE` the
    segment — never `set_data`.
  - **current:** attach view (`track=False`), `set_data(...)` on the main thread;
    then for the *previous* `held` segment, close its view and `FREE` it (now
    superseded — SciQLopPlots no longer references it). The new segment becomes
    `held`.
- **Worker, on FREE:** mark segment reusable.

Invariant: **the worker only ever writes a segment that no `set_data` currently
references.** Every segment handed out is returned by exactly one `FREE` (after
supersession, or immediately if dropped) — no leaks. Pool size is emergent
(≈ max in-flight + 1, typically 2–3), grows on demand, never shrinks below need.

### 5.3 Ownership / `resource_tracker`

Worker is the **sole** creator and unlinker (`track=True`, explicit unlink on
shutdown/shrink). Main attaches **`track=False`** (Python 3.13+) and only ever
`close()`s — never unlinks. This sidesteps the `multiprocessing.shared_memory`
`resource_tracker` premature-unlink bug entirely.

### 5.4 Coalescing on both ends

Consumer drops stale replies by `req_id`; producer, between computes, drains the
pipe, applies pending `FREE`s, and keeps only the **latest** `REQUEST` per
channel — skipping superseded compute outright.

## 6. Worker loop & reduction

```
on INSTALL: callables[channel_id] = cloudpickle.loads(blob)
loop:
  msg = conn.recv()                 # block for the first
  drain all conn.poll(0) messages   # batch what is already queued
  apply every FREE  → pool.mark_reusable(seg)
  per channel: keep only the LATEST REQUEST
  for (channel, req_id, start, stop):
      try:    result = callables[channel](start, stop)
      except: send ERROR(channel, req_id, traceback.format_exc()); continue
      if result is None: send EMPTY(channel, req_id); continue
      arrays, arity = reduce(result)
      seg = pool.acquire(channel, total_nbytes(arrays))
      write arrays back-to-back into seg
      send RESULT(channel, req_id, seg.name, [(shape, dtype, offset)...], arity)
```

`reduce(result)` — one place, declarative on type:

- `SpeasyVariable` spectrogram → `(time_epoch_f64, freq, z_f32)`, arity 3;
  scalar/vector → `(time, values)`, arity 2
- `(time, y)` → arity 2; `(time, y, z)` → arity 3
- `None` → `EMPTY` (no segment)

All arrays forced contiguous, native dtype. One segment holds all N arrays at
offsets; the main side builds N typed views into it.

## 7. User opt-in & plot-path integration

- **API:** one new kwarg, `out_of_process: bool = False`, on
  `create_virtual_product` and the plugin-facing factories
  (`VirtualSpectrogram`, `make_rich_vp`, …). Radio becomes
  `make_rich_vp(..., out_of_process=True)`.
- **At registration:** `RemoteRegistry.register(path, callback)` does
  `cloudpickle.dumps(callback)` **immediately** → fails fast naming the product
  if it cannot pickle. The product node still lands in the tree (metadata,
  plot_hints intact), tagged `remote=True`.
- **Worker grouping:** `plugin_key = callback.__module__.split(".")[0]` — all of
  a plugin's remote products share one worker. No new author input.
- **Plot path:** in `time_sync_panel.plot_product`, a single branch — remote node
  → `add_remote_color_map` / `add_remote_line_graph` by graph type,
  `ch = g.remote_channel()`, get-or-spawn the `RemoteWorker` for `plugin_key`,
  `INSTALL` once, bind a `RemoteChannel` wiring `ch.data_requested → worker`.
  The non-remote path is untouched.

## 8. Code-hygiene prerequisite (radio plugin)

`_open_and_convert` currently lives in `sciqlop_radio/dock.py`, which imports
PySide6 at module level. cloudpickle-by-reference would re-import that module in
the worker, dragging Qt in for no functional reason (the actual reader,
`reader.open_spectrogram`, is already Qt-free). **Move `_open_and_convert` (and
any other compute referenced by the callback) into a Qt-free module** so the
worker never imports Qt. This is good separation regardless of approach. (Radio
plugin change, out of the SciQLop tree.)

## 9. Lifecycle & error handling

- **Worker death:** pipe EOF → `QSocketNotifier` fires → `recv` raises → mark
  dead, clear `busy` on affected channels, log; **respawn lazily** on the next
  `data_requested`.
- **Graph teardown** (`docs/qt-lifetime-patterns.md`): `RemoteChannel.dispose()`
  sends `RELEASE`, `FREE`s the `held` segment, closes views — wired via a
  context-bound slot on `destroyed` that uses the **cached `channel_id`**, never
  `self._graph.…`. This is the SIGSEGV-in-`sharedPainter` guard.
- **shm cleanup:** worker is sole unlinker — `RELEASE` unlinks a channel's
  segments, `SHUTDOWN` unlinks all. Hard-kill leak mitigated by a
  `sciqlop_<pid>_*` name prefix + best-effort sweep of stale segments on worker
  start.
- **Errors → UI:** `ERROR` traceback surfaces in SciQLop's log widget, same
  channel as today's `_CallbackErrorOverlay`.
- **Backpressure:** `busy()` is auto-managed by SciQLopPlots (request → set_data);
  coalescing prevents pile-up. No extra work.

## 10. Testing (test-first)

1. **In-process protocol tests** (no subprocess) — fake local responder; pin the
   race-free rule: stale-drop, `FREE` accounting (every segment returned exactly
   once), never reuse a held segment. Mirrors SciQLopPlots'
   `test_zero_copy_shared_memory_buffer`. **Written first, red before the pool
   exists.**
2. **Worker-loop unit tests** — in-memory pipe pair; assert
   `RESULT`/`ERROR`/`EMPTY`, reduction correctness (dtypes preserved, contiguous),
   coalescing.
3. **End-to-end subprocess test** — real spawned worker, trivial pickled
   callable, pan a real `add_remote_color_map`; **subprocess-isolated** (kernel-
   test Shiboken lesson).
4. **Crash/teardown tests** — kill worker mid-flight → recovers, no crash; destroy
   graph → dispose never touches the dead graph.
5. **Reducer fuzz** — float32/float64 shapes; assert no `std::terminate` dtype
   path.

## 11. New dependency & pickle trust boundary

`cloudpickle` (small, standard) — stdlib `pickle` cannot serialize closures /
lambdas, which the radio callback uses.

**Trust boundary:** the cloudpickled callable flows from the main SciQLop process
to a worker subprocess that **SciQLop itself spawns**, over a **private pipe**,
within a single trust domain. The callable originates from an already-loaded,
already-privileged plugin running in-process — unpickling it in the worker grants
no capability the plugin did not already have. No pickle data is ever read from an
external or untrusted source (no network, no user file, no cross-user channel), so
this is not an RCE vector beyond the plugin's existing reach. If remote *plugins*
were ever sourced from untrusted registries, that risk lives at the plugin-install
gate, not here — and is out of scope for this design.
