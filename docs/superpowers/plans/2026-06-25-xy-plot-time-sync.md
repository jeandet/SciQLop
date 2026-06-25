# XY Plot Auto Time-Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A function/callback plotted into a plain XY plot inside a TimeSync panel is driven by the panel's time window automatically, so users no longer hand-wire `panel._impl.time_range_changed.connect(g._impl.set_range)`.

**Architecture:** Callback graphs in SciQLopPlots observe an axis (`range_changed → call`), defaulting to the plot's own X axis. For a plain XY plot that X axis is the data/frequency axis, so the callback never sees panel time changes. We add a small SciQLop-side helper that, for plain XY plots only, re-points the function graph to observe the plot's `time_axis()` (which the panel drives). `observe()` disconnects the prior observation first, so this *replaces* the frequency-axis wiring — no double trigger. Time-series plots (X axis already is time) and projection plots (own time machinery) are excluded.

**Tech Stack:** Python, PySide6/Shiboken6, SciQLopPlots C++ bindings, pytest + pytest-qt + pytest-xvfb.

**Spec:** `docs/superpowers/specs/2026-06-25-xy-plot-time-sync-design.md`

---

## Running the tests

The `plot_panel` fixture pulls in the full `main_window` (plugins load `QWebEngineView`).
On a real display use the project's canonical command:

```bash
uv run pytest tests/test_xy_plot_time_sync.py -v
```

In a **headless sandbox**, WebEngine needs software GL or it segfaults. Use this prefix
(verified working in this environment) — referred to below as `$PYTEST`:

```bash
PYTEST="xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 QT_OPENGL=software QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu\ --no-sandbox\ --in-process-gpu QTWEBENGINE_DISABLE_SANDBOX=1 uv run pytest"
```

**Import rule (load-bearing):** `SciQLop.user_api.plot` and `SciQLop.components...time_sync_panel`
must be imported **inside test functions**, never at module top — a top-level import touches
the `ProductsModel` Qt global static before a `QApplication` exists and aborts during
collection. `from .fixtures import *` at the top is safe.

---

## File structure

- **Modify:** `SciQLop/components/plotting/ui/time_sync_panel.py`
  - add `import math` (currently absent)
  - add `_is_plain_xy_plot(plot)` — className gate (works on concrete plots and on `SciQLopPlotInterfacePtr`)
  - add `_time_sync_callback_graph(plot, graph)` — the re-point + initial refresh
  - call `_time_sync_callback_graph(plot, graph)` inside `plot_function` after `plot, graph = r`
- **Create:** `tests/test_xy_plot_time_sync.py` — reproducer + regression + gate-logic tests

---

### Task 1: Failing reproducer — XY function plot ignores panel time changes

**Files:**
- Create: `tests/test_xy_plot_time_sync.py`

- [ ] **Step 1: Write the failing test**

```python
"""Auto time-sync of callback graphs in plain XY plots.

SciQLop.user_api.plot / time_sync_panel are imported INSIDE tests on purpose:
a top-level import touches the ProductsModel Qt global static before a
QApplication exists and aborts during collection.
"""
from .fixtures import *
import numpy as np
import pytest


def test_xy_function_plot_is_time_synced_to_panel(plot_panel, qtbot):
    from SciQLop.core import TimeRange
    from SciQLop.user_api.plot import PlotType

    seen = []

    def spectrum(start, stop):
        seen.append((float(start), float(stop)))
        return np.linspace(0.01, 1.0, 16), np.ones(16)

    t0 = 1.7e9
    # a time-series anchor on plot 0
    plot_panel.plot_data(np.array([t0, t0 + 1, t0 + 2]),
                         np.array([1.0, 2.0, 3.0]))
    # XY function on a new plot — NO manual time_range_changed.connect
    plot_panel.plot_function(spectrum, plot_index=1, plot_type=PlotType.XY,
                             labels=["spec"])

    seen.clear()
    plot_panel.time_range = TimeRange(t0 + 200, t0 + 300)
    qtbot.wait(80)

    assert seen, "XY function callback was not invoked on a panel time-range change"
    assert seen[-1] == pytest.approx((t0 + 200, t0 + 300))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$PYTEST tests/test_xy_plot_time_sync.py::test_xy_function_plot_is_time_synced_to_panel -v -s`
Expected: **FAIL** at `assert seen` — the callback is wired to the XY plot's frequency axis, so the panel time change never fires it (`seen` stays empty). This reproduces the bug.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_xy_plot_time_sync.py
git commit -m "test(plotting): reproduce XY function plot not time-synced to panel"
```

---

### Task 2: Implement the helper and wire it into `plot_function`

**Files:**
- Modify: `SciQLop/components/plotting/ui/time_sync_panel.py`

- [ ] **Step 1: Add `import math` near the top of the module**

`time_sync_panel.py` has no `math` import. Add it with the other stdlib imports at the top of the file (e.g. just below the existing import block, before the first `from SciQLopPlots ...` line):

```python
import math
```

- [ ] **Step 2: Add the gate + helper just above `def plot_function(` (line ~701)**

```python
def _is_plain_xy_plot(plot) -> bool:
    """A plain XY plot whose X axis carries data, not time.

    Excludes time-series plots (X axis already *is* the synced time axis, so
    callback graphs are time-driven by construction) and projection plots
    (own time machinery). Uses the C++ class name so it also works on
    ``SciQLopPlotInterfacePtr`` handles returned by the panel.
    """
    return plot.metaObject().className() not in (
        "SciQLopTimeSeriesPlot", "SciQLopNDProjectionPlot")


def _time_sync_callback_graph(plot, graph) -> None:
    """Re-point a callback graph in a plain XY plot to observe the panel's
    time axis instead of the plot's own (data) X axis, so ``f(start, stop)``
    is driven by the panel time window.

    ``observe()`` clears its previous observer connections first, so this
    replaces the default frequency-axis wiring rather than stacking on it.
    No-op for time-series / projection plots, and for graphs that are not
    callback graphs (``observe`` is only defined on function-graph types).
    """
    if not _is_plain_xy_plot(plot):
        return
    if not hasattr(graph, "observe"):
        return
    graph.observe(plot.time_axis())
    time_range = plot.time_axis().range()
    if math.isfinite(time_range.start()) and math.isfinite(time_range.stop()):
        graph.set_range(time_range)
```

- [ ] **Step 3: Call the helper inside `plot_function`**

In `plot_function`, the body currently reads:

```python
    try:
        plot, graph = r
        reporter.attach(plot)
        panel_name = target.windowTitle() if hasattr(target, "windowTitle") else ""
```

Insert the helper call right after `reporter.attach(plot)`:

```python
    try:
        plot, graph = r
        reporter.attach(plot)
        _time_sync_callback_graph(plot, graph)
        panel_name = target.windowTitle() if hasattr(target, "windowTitle") else ""
```

- [ ] **Step 4: Run the reproducer to verify it now passes**

Run: `$PYTEST tests/test_xy_plot_time_sync.py::test_xy_function_plot_is_time_synced_to_panel -v -s`
Expected: **PASS** — `seen[-1] == (t0+200, t0+300)`; the XY callback now receives the panel time window.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/ui/time_sync_panel.py
git commit -m "fix(plotting): time-sync callback graphs in XY plots to the panel

Function/callback graphs in a plain XY plot observed the plot's own
(frequency/data) X axis, so panel time-range changes never refreshed them
and users had to hand-wire panel._impl.time_range_changed -> graph._impl.
set_range. Re-point such graphs to observe the plot's time_axis() instead.
No-op for time-series plots (X axis already is the time axis) and projection
plots (own time machinery)."
```

---

### Task 3: Regression — time-series unaffected + gate logic

**Files:**
- Modify: `tests/test_xy_plot_time_sync.py`

- [ ] **Step 1: Append the regression tests**

```python
def test_timeseries_function_plot_still_time_synced(plot_panel, qtbot):
    """The no-op path: time-series function plots already observe the time
    axis (their X axis), and must keep refreshing on time changes."""
    from SciQLop.core import TimeRange

    seen = []

    def line(start, stop):
        seen.append((float(start), float(stop)))
        t = np.linspace(start, stop, 10)
        return t, np.sin(t)

    plot_panel.plot_function(line)  # default plot_type=TimeSeries

    seen.clear()
    t0 = 1.7e9
    plot_panel.time_range = TimeRange(t0, t0 + 50)
    qtbot.wait(80)

    assert seen, "time-series function callback not invoked on time change"
    assert seen[-1] == pytest.approx((t0, t0 + 50))


def test_gate_excludes_timeseries_and_projection(qapp):
    """`_is_plain_xy_plot` keys off the C++ class name so it works on both
    concrete plots and SciQLopPlotInterfacePtr handles."""
    from SciQLop.components.plotting.ui.time_sync_panel import _is_plain_xy_plot

    class _FakeMeta:
        def __init__(self, name):
            self._name = name

        def className(self):
            return self._name

    class _FakePlot:
        def __init__(self, name):
            self._meta = _FakeMeta(name)

        def metaObject(self):
            return self._meta

    assert _is_plain_xy_plot(_FakePlot("SciQLopPlot")) is True
    assert _is_plain_xy_plot(_FakePlot("SciQLopTimeSeriesPlot")) is False
    assert _is_plain_xy_plot(_FakePlot("SciQLopNDProjectionPlot")) is False
```

- [ ] **Step 2: Run the full test file**

Run: `$PYTEST tests/test_xy_plot_time_sync.py -v -s`
Expected: **3 passed** (reproducer + time-series regression + gate logic).

- [ ] **Step 3: Commit**

```bash
git add tests/test_xy_plot_time_sync.py
git commit -m "test(plotting): time-series no-op + gate-logic coverage for XY time-sync"
```

---

### Task 4: Guard against regressions in the wider plotting suite

**Files:** none (verification only)

- [ ] **Step 1: Run the plotting-related test files**

Run:
```bash
$PYTEST tests/test_histogram2d.py tests/test_plot_scatter_hline.py tests/test_plot_y2_axis.py tests/test_graph_context_integration.py tests/test_overlay.py -v
```
Expected: **all pass** — the helper is a no-op for every existing path (histogram2d wires time itself; time-series/projection are excluded; static-data plots create no callback graph).

- [ ] **Step 2: If anything fails**, read the failure and reconcile against the spec before changing the helper. Do not weaken the gate to paper over a real regression. Commit only once green.

---

## Self-Review

**1. Spec coverage:**
- "function in a plain XY plot is time-synced by default" → Task 1 (test) + Task 2 (helper + wiring). ✓
- "re-point via `observe(time_axis())`, replaces not stacks" → Task 2 Step 2. ✓
- Scope gate (XY apply / time-series no-op / projection excluded / not-in-panel inert) → `_is_plain_xy_plot` + the `time_axis()` being undriven outside a panel (helper still runs but never fires). Task 3 gate test + Task 3 time-series test. ✓
- "initial draw if panel already has a finite time range" → Task 2 Step 2 (`math.isfinite` guard + `set_range`). ✓
- TDD step 0 risk (does the returned graph expose `observe`) → resolved during planning by probe: the graph impl is the concrete `SciQLopCurveFunction` and has `observe`; the `hasattr(graph, "observe")` guard keeps the helper safe if that ever changes. ✓
- Out of scope (`transform=`/`derive()`, histogram2d unify, SciQLopPlots edit, `plot_product`-into-XY) → not in any task. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows full code; every run step has a command and expected result. ✓

**3. Type consistency:** `_is_plain_xy_plot(plot)` and `_time_sync_callback_graph(plot, graph)` names match between definition (Task 2) and use (Task 2 Step 3, Task 3 gate test). `plot.time_axis()` returns a `SciQLopPlotAxisInterface` with `.range()` → `SciQLopPlotRange` with `.start()`/`.stop()` methods (consistent with existing `plot.x_axis().range()` usage at `time_sync_panel.py:727`). ✓
