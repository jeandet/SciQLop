# Auto Time-Sync for Callback Graphs in XY Plots — Design

**Date:** 2026-06-25
**Status:** Approved

## Motivation

Plotting a *time-window transform* (FFT, hodogram, A-vs-B scatter, phase-space) on a
synced XY plot today requires hand-wiring the panel's time range into the graph:

```python
panel.plot_product(B_TREE, plot_index=0)                       # |B| time series
xy, g = panel.plot_function(b_fft, plot_index=1,               # time-synced XY FFT
                            plot_type=PlotType.XY, labels=["|B| spectrum"])
panel._impl.time_range_changed.connect(g._impl.set_range)      # <-- the hack
```

That last line reaches through `._impl` on **both** the public `PlotPanel` and the
public `Graph` to forward time-range changes into the XY graph's refresh. Users should
never touch `._impl`, and they shouldn't have to know that an XY plot's callback isn't
driven by the panel time range out of the box.

The goal: a function/callback plotted into a plain XY plot inside a TimeSync panel is
**time-synced by default**, so the line above disappears.

## Current behavior (why the hack is needed)

Callback graphs are wired by SciQLopPlots to *observe* an axis
(`SciQLopPlot::_connect_callable_sync`, `src/SciQLopPlot.cpp:943`): with no explicit
`sync_with`, the graph observes `this->x_axis()`. `observe(axis)`
(`src/SciQLopGraphInterface.cpp:75`) connects that axis's `range_changed` to the
callback:

```cpp
connect(axis, &range_changed, as_graph,
        [this](const SciQLopPlotRange& range){ this->call(range); });
```

The plot type only changes *what `x_axis()` is*:

- **TimeSeriesPlot** — `x_axis()->set_is_time_axis(true)`
  (`src/SciQLopTimeSeriesPlot.cpp:31`); the X axis **is** the time axis, kept synced
  across subplots by the panel. Observing X == observing time → callbacks refresh on
  time changes. Works by construction.
- **Plain XY plot** (`SciQLopPlot`, `BasicXY`) — `x_axis()` is the **frequency/data**
  axis. The callback is wired to *frequency-axis* `range_changed`, so changing the
  panel time range never re-fires it (and a frequency-axis zoom would call
  `b_fft(freq_lo, freq_hi)` with frequencies in place of a time window).

`PlotPanel.histogram2d` papers over this for its own callback path by manually
connecting `impl.time_range_changed.connect(hist._impl.set_range)`
(`SciQLop/user_api/plot/_panel.py:265`); `plot_function` has no equivalent.

## Key facts (verified)

- Every `SciQLopPlot` exposes a `time_axis()` — a `SciQLopPlotDummyAxis`
  (`include/.../SciQLopPlotAxis.hpp:250`, a `SciQLopPlotAxisInterface`) the panel drives
  on every range change (`SciQLopPlotContainer.hpp:181`:
  `plot->time_axis()->set_range(range)`). Runtime-introspected as exposed on
  `SciQLopPlot`, `SciQLopTimeSeriesPlot`, `SciQLopNDProjectionPlot`.
- `observe()` is exposed on the concrete function-graph types
  (`SciQLopLineGraphFunction`, `SciQLopSingleLineGraphFunction`, `SciQLopCurveFunction`),
  **not** on the base `SciQLopGraphInterface`. `set_range` is on everything.
- `observe()` disconnects prior observer connections before connecting
  (`src/SciQLopGraphInterface.cpp:77-80`), so re-pointing **replaces** rather than
  stacks — no double-trigger.

## Approach

A single helper in `SciQLop/components/plotting/ui/time_sync_panel.py`, called from the
impl `plot_function` (the choke point behind both `PlotPanel.plot_function` and
`PlotPanel.plot()`'s callable dispatch). It re-points the function graph to observe the
plot's **time axis** instead of the frequency X axis:

```python
graph.observe(plot.time_axis())   # replaces the default x_axis observation
```

The callback contract becomes uniform across the API: `f(start, stop)` always means
"the current panel time window" — same as `plot_product`, virtual products, and layers.

### Scope gate

- **Plain XY plot** (`not is_time_series_plot(plot) and not is_projection_plot(plot)`)
  → apply the re-point.
- **Time-series plot** → **no-op** (`x_axis() == time_axis()`, already correct).
- **Projection plot** → **excluded** (has its own time-driven machinery; re-pointing
  could break it).
- **Not in a panel** → `time_axis()` exists but isn't driven, so the wire is inert.
  Safe; no special-casing needed.

### Implementation risk to pin first (TDD step 0)

The handle `target.plot(...)` returns is declared `SciQLopGraphInterface*` in C++;
Shiboken may surface it as the base interface (no `observe`) rather than the concrete
`…GraphFunction` — the same "interface Ptr lacks patched methods" trap already known for
`panel.plots()`. The first test probes whether the returned graph exposes `observe`.

- If concrete (has `observe`) → use the re-point directly.
- If base → resolve the concrete plottable from `plot.plottables()` and `observe` on it.
- If `observe` is unreachable either way → fall back to
  `panel.time_range_changed.connect(graph.set_range)` (mirrors `histogram2d`; accepts a
  benign additive frequency-axis trigger that autoscale signal-suppression already makes
  harmless in practice).

### Initial draw

After wiring, if the panel already holds a finite time range, trigger one
`graph.set_range(time_range)` so a plot created *after* `panel.time_range` was set still
draws immediately (a panel that has never had a time range set returns `(NaN, NaN)` from
`time_axis_range()` — guard with `math.isfinite`).

## Testing

Reproducer first (red → green), using the `plot_panel` fixture (pytest-qt):

1. **Time-sync reproducer** — time-series product on plot 0, a spy callback on an XY
   plot (plot 1) via `plot_function`, **no** manual connect. Set `panel.time_range` to a
   known window; assert the spy was invoked with *that time window* and that data was
   set. Fails before the patch, passes after.
2. **Callback receives time, not frequency** — assert the `(start, stop)` the spy sees
   are the panel time bounds, never the XY plot's own axis range.
3. **Regression: time-series function plot** still refreshes on time change (no-op path
   unaffected).
4. **Regression: projection** plot path unchanged (excluded by the gate).

## Out of scope (mentioned, not built)

- `transform=` / `derive()` sugar to retire the duplicate `B_UID` re-fetch and the
  hand-rolled FFT (let the framework fetch the source once and feed `dsp.fft` the
  `SpeasyVariable`). `observe(graph)` (`SciQLopGraphInterface.cpp:86`, source-graph
  `data_changed → call(x, y)`) is the C++ primitive that would power it.
- Unifying `histogram2d`'s manual time-connect onto the same helper.
- Any change to SciQLopPlots itself (the ideal fix — defaulting the C++ `sync_with` to
  the time axis for non-time-series plots — is left to the SciQLopPlots maintainer).
