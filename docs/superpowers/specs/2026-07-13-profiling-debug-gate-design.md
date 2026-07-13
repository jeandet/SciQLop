# Gate new profiling tools behind `SCIQLOP_DEBUG`

**Date:** 2026-07-13
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — `core/sciqlop_application.py`,
`components/profiling/menu.py`, `components/sciqlop_logging/logger.py`).

## Problem

The last few days' profiling work (commits `2b58ca8b`..`675b20e3`) added a
hot-thread ranker, a hang-dump signal handler, an always-on-by-default GUI
responsiveness watchdog, and a sampling profiler — all wired to start
unconditionally at every `SciQLopApp` startup, plus a `Tools > Profiling`
menu always visible to every user. None of this is useful to a regular
SciQLop user; it's debug/diagnostic tooling that should not run or appear
unless someone opts in.

## Design

### Master switch: reuse `SCIQLOP_DEBUG`

SciQLop already has `SCIQLOP_DEBUG` (`components/sciqlop_logging/logger.py:7`,
sets debug log level). Add a small helper there:

```python
def is_debug_mode() -> bool:
    return 'SCIQLOP_DEBUG' in os.environ
```

Exported from `SciQLop.components.sciqlop_logging`. Reused instead of adding
a second, profiling-specific env var — one debug switch for the whole app.

### Gated: startup wiring (`core/sciqlop_application.py:45-50`)

```python
hang_dump.install_signal_dump()
sampler.maybe_start_from_settings()
self._watchdog = watchdog.Watchdog()
self._watchdog.start()
self._watchdog_timer = watchdog.start_qt_heartbeat(self._watchdog)
```

wrapped in `if is_debug_mode():`. When off: no SIGUSR1 handler armed, no
watchdog thread, no QTimer heartbeat, sampler never auto-starts.
`self._watchdog`/`self._watchdog_timer` are set to `None` in the `else`
branch (nothing outside this file/tests reads them, confirmed by grep).

### Gated: three debug-only actions in `Tools > Profiling`

The `Profiling` submenu (`components/profiling/menu.py`, wired from
`core/ui/mainwindow.py:164-166`) **stays unconditionally present** — it also
hosts the pre-existing Perfetto/`SCIQLOP_TRACE` trace controls, which are out
of scope for this change (see below).

Inside `ProfilingMenu.__init__`, only add these three actions (and the
separator immediately preceding them) when `is_debug_mode()` is true:
- "Show hot OS threads…"
- "Dump thread stacks now"
- "Flush sampling history"

The trace Start/Stop, Open last/Open trace in Perfetto, and status actions
are built unconditionally, exactly as today.

### Explicitly out of scope (left untouched)

- `SCIQLOP_TRACE` / Perfetto tracing: `core/tracing.py`,
  `tracing.zone`/`counter`/async-span calls on the remote-worker hot path
  (`worker_handle.py`, `channel.py`), worker-subprocess trace merge
  (`worker.py`, `menu.py:_on_stop`), and the trace Start/Stop/Open/status
  menu actions. This mechanism predates the profiling work being gated here
  and already has its own env-var (`SCIQLOP_TRACE` is a path, read by
  SciQLopPlots' native static init, not by this repo).
- `SciQLop/user_api/diagnostics.py` — console-facing API
  (`install_signal_dump`, `dump_now`, `hot_threads`, etc.) stays importable
  and callable as-is. A user who explicitly imports and calls it from the
  Jupyter console is opting in, not being surprised by background overhead
  or menu clutter.
- `ProfilingSettings` (`components/profiling/settings.py`) fields are
  unchanged; they only take effect once debug mode is on.

### CI impact

`.github/workflows/tests.yml` already sets `SCIQLOP_DEBUG: 1`, so CI
continues to exercise the watchdog/hang-dump/sampler/menu-actions code paths
exactly as before. Locally, `uv run pytest` without `SCIQLOP_DEBUG` set will
simply not start these background pieces during the test session — a
(desirable) reduction in local test overhead, not a functional regression.

## Testing

TDD: write a failing test for `is_debug_mode()` first
(`monkeypatch.setenv`/`delenv('SCIQLOP_DEBUG')`), then implement it.

The two gated call sites (`sciqlop_application.py`, `menu.py`) are one-line
`if is_debug_mode():` guards around existing, already-tested code — not
separately unit-tested. The fixtures that construct `SciQLopApp` /
`SciQLopMainWindow` (`qapp`, `main_window` in `tests/fixtures.py`) are
session-scoped and shared across the whole test suite, so toggling the env
var per-test to assert on their gating isn't practical there. Full suite run
once at the end to confirm no regressions (existing `test_watchdog.py`,
`test_profiling_settings.py` exercise the underlying classes directly and
are unaffected by this gating).
