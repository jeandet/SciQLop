# User API Fuzzing Report — 2026-06-12

> **STATUS (fixed 2026-06-12, same day):** #1, #3–#19 are all fixed with
> regression tests in `tests/test_graphic_primitives.py` and
> `tests/test_user_api_validation.py`. Root cause of #1 was the
> `panel.plots` enumeration path (wrappers holding `SciQLopPlotInterfacePtr`);
> `plot_data`-returned plots were never affected. #8's "silent None" was the
> protocol's `plot_type` stub plus the window before deferred deletion —
> stale wrappers did already raise; `plot_type` is now a real property.
> #19 was already intentional Python-style indexing — now documented.
> Remaining: **#2** (Shiboken error-handler NameError) and **#20** (garbage
> data renders as pixel noise) belong in the SciQLopPlots repo — not yet filed.

Live crash-hunting session against a running SciQLop instance (`SciQLop - default`
workspace), driving `SciQLop.user_api` through the embedded IPython kernel.
~60 abuse cases across plotting, panels, primitives, and file I/O.

**Headline: no segfault, no process crash.** But one public feature is completely
broken, one binding bug masks every misuse error, panel deletion can corrupt the
dock layout, and there are several silent failures that need idiot-proofing.

All findings were reproduced live; every snippet below is a verified reproducer.
Per global workflow rules: **write a failing test first for each fix**.

---

## 🔴 Critical

### 1. ALL graphic primitives are broken (Text, Ellipse, CurvedLine, Pixmap, HorizontalLine, add_hline)

Any construction — including the documented happy path — fails:

```python
from SciQLop.user_api import plot as P
panel = P.create_plot_panel()
plot, _ = panel.plot_data([1, 2, 3], [4, 5, 6])
P.Text(plot, 'hello', 0.5, 0.5)
# NameError: Error evaluating `SciQLopPlotsBindings.SciQLopTextItem.__init__`:
# name 'SciQLopPlotsBindings' is not defined
plot.add_hline(1.0)   # same failure (SciQLopHorizontalLine)
```

**Root cause (verified live):** `plot._get_impl_or_raise()` returns a
`SciQLopPlotInterfacePtr` (Shiboken smart-pointer wrapper class). The C++ item
constructors only accept the dereferenced object. Verified fix:

```python
impl = plot._get_impl_or_raise()
SciQLopPlotsBindings.SciQLopHorizontalLine(impl.data(), 5.0)   # works
SciQLopPlotsBindings.SciQLopHorizontalLine(impl, 5.0)          # NameError above
```

**Fix:** deref the Ptr in every constructor call site in
`SciQLop/user_api/plot/_graphic_primitives.py` (e.g. a small
`_deref(impl)` helper that calls `.data()` when present), or make the
SciQLopPlots bindings accept the Ptr type. Note `_get_impl_or_raise()` is
presumably also used elsewhere — audit other call sites that pass the result
into binding constructors.

### 2. Shiboken error-handler masks the real TypeError with a NameError

When overload resolution fails on any `SciQLopPlotsBindings` call, the
signature-error formatter itself raises
`NameError: name 'SciQLopPlotsBindings' is not defined` instead of the real
`TypeError` listing accepted overloads. Seen on every primitive ctor (issue #1)
and also:

```python
panel.plot_function(42)
# NameError: Error evaluating `SciQLopPlotsBindings.SciQLopPlotCollectionInterface.line`: ...
```

This is a SciQLopPlots binding-generation / signature-module issue (the eval
namespace used by shibokensupport's error handler lacks the module name).
Fixing it makes every downstream misuse diagnosable again. Likely belongs in
the SciQLopPlots repo, not here — but track it.

### 3. Deleting a panel's impl widget corrupts the dock layout for OTHER panels

```python
victim = P.create_plot_panel()        # 'Panel1' (while 'Panel0' exists)
victim._impl.close()
victim._impl.deleteLater()
```

Observed aftermath:
- **Panel0** (untouched!) ended up with its `CDockWidget` unparented from any
  dock area: `isVisible()==False`, `isHidden()==False`, parent chain dead-ends
  at the CDockWidget. Invisible and unrecoverable from the GUI.
- `Panel1` stayed as a zombie entry in `CDockManager.dockWidgetsMap()`.
- The MCP/main-window panel enumeration (`window_state`, `list_panels`)
  reported `panel_count: 0` while `plot_panel('Panel0')` still returned a live,
  fully functional panel with 16 plots — and kept reporting 0 even after the
  dock widget was manually re-added and made visible again.

Yes, calling `close()/deleteLater()` on the inner `TimeSyncPanel` is abuse —
but the failure radius (corrupting a *sibling* panel, permanent registry
desync) is too large. The panel registry should be robust against the impl
widget dying: hook `destroyed` on the TimeSyncPanel / dock widget and clean up
both the registry and the dock entry.

---

## 🟠 Silent failures (idiot-proofing)

| # | Reproducer | Observed | Expected |
|---|---|---|---|
| 4 | `panel.save('/nonexistent/dir/x.png')` | returns None, **no file, no error** | raise `IOError`/`OSError` |
| 5 | `panel.save('/root/forbidden.png')` (no permission) | same silent OK | raise |
| 6 | `P.TimeRange('garbage', 'dates')` | silently → `1970-01-01 .. 1970-01-01` | raise `ValueError` |
| 7 | `panel.time_range = P.TimeRange(nan, nan)` | accepted; panel time range corrupted to 1970 | reject non-finite |
| 8 | stale `TimeSeriesPlot` wrapper after `panel.remove_plot(i)` | `plot_type`/`replot()`/`set_y_range()` all silently return `None` | raise, like stale *panels* already do (`ValueError: The plot panel does not exist anymore`) — make it consistent |
| 9 | `panel.plot_function(f)` where `f` raises | traceback only on console; plot created "successfully", stays empty forever | surface the error on `plot.overlay` (Error level) — the overlay API exists for exactly this |
| 10 | `panel.plot_product('does//not//exist')` (and `''`, `None`, `42`, `[]`, bad lists) | `TypeError: cannot unpack non-iterable NoneType object` — internal unpack of a None return | `ValueError: product 'does//not//exist' not found` |

Note on #8: panel-level lifetime guarding is **good** (clean ValueError through
sub-panels too). Plot/graph wrappers should get the same treatment instead of
the silent no-op path.

---

## 🟡 Validation gaps (lower priority)

| # | Reproducer | Observed |
|---|---|---|
| 11 | `panel.histogram2d(x, y, x_bins=0, y_bins=0)` | accepted |
| 12 | `panel.histogram2d(x, y, x_bins=-5)` | accepted |
| 13 | `panel.histogram2d(x, y, x_bins=10_000, y_bins=10_000)` | 100M-cell grid accepted, no sanity cap |
| 14 | `panel.plot_data(t, None)` | accepted, creates a plot |
| 15 | `panel.plot_data(np.array(1.0), np.array(2.0))` (0-d) | accepted |
| 16 | `panel.plot_data(t, complex_array)` | silently casts, drops imaginary part (numpy ComplexWarning only) |
| 17 | `panel.zoom_limit_seconds = -5` | accepted |
| 18 | `P.plot_panel(42)` | raw Shiboken TypeError leaking `CDockManager.findDockWidget` internals — validate `name: str` at the API boundary |
| 19 | `panel.remove_plot(-1)` | accepted (negative index). If intended, document it; double `remove_plot(0)` removes two *different* plots due to index sliding — at least document |
| 20 | rendering: plots fed object-dtype / non-monotonic / garbage data render as **random pixel noise** (looks like uninitialized buffer) — screenshot evidence from live session; investigate in SciQLopPlots |

---

## ✅ What held up well (don't break these)

- `plot_data` length-mismatch check: `RuntimeError: length mismatch: x has 100, y has 50`
- `plot_data` ndim check: `RuntimeError: y: ndim must be 1 or 2 (got 3)`
- string arrays rejected with clear ValueError
- axis-name validation: `ValueError: axis 'bogus_axis' not available on this plot (expected one of: x, y, y2, z)`
- `remove_plot` bounds check: `IndexError: plot_index 999 out of range (0..8)`
- stale **panel** guard: `ValueError: The plot panel does not exist anymore` (incl. sub-panels)
- `save()` extension validation: `ValueError: Unsupported format '.unsupported_ext'. ...`
- `add_layer` bad index: clean IndexError
- No crash from: NaN/inf data, empty arrays, inverted/NaN ranges, log scale on
  negative range, 100k-char overlay text, `step_forward(10**9)`, huge panel names.

---

## Suggested attack order for the fixing instance

1. **#1** — one-line-ish deref fix in `_graphic_primitives.py`, restores a whole
   public feature. Test: create each primitive on a live plot.
2. **#10** — `plot_product` error message (pure Python, trivially testable).
3. **#8** — stale plot wrappers raise instead of silent None (align with panel behavior).
4. **#9** — route plot_function/fetch errors to `plot.overlay`.
5. **#4/#5** — `save()` raises on write failure (check file exists / Qt save return value).
6. **#6/#7** — TimeRange parse/NaN validation.
7. **#3** — panel/dock lifecycle hardening (needs more design thought).
8. Remaining 🟡 items as a validation sweep.
9. **#2** and **#20** → file in the SciQLopPlots repo instead.

> **Round 2** (post-fix re-fuzz + new surfaces: catalogs, virtual products,
> graph ops, overlay, layers) lives in its own report:
> `api-fuzzing-report-round2-2026-06-12.md`. Note it found **#6 only
> partially fixed** (string-parse path of `TimeRange` still silent).
