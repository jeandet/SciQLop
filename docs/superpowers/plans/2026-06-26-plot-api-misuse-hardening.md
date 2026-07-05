# Plot API Misuse Hardening (SciQLop user_api) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public plot API discoverable and misuse-resistant by promoting load-bearing `**kwargs` options to explicit, documented keyword-only parameters — without breaking any existing call site.

**Architecture:** A single sentinel (`_UNSET`) plus a `_with_explicit(kwargs, **named)` helper folds caller-set keyword params back into the forwarded kwargs dict, forwarding a value only when the caller actually set it. This preserves the exact present/absent semantics the `**kwargs` passthrough had. All new params are keyword-only (after `*`), so no positional ordering can change. `**kwargs` is retained on every method for niche/graph-specific options.

**Tech Stack:** Python 3.14, PySide6, pytest + pytest-qt + pytest-xvfb. Run tests with `uv run pytest` (canonical local run: `uv run pytest --no-xvfb`).

**Scope note:** This is the SciQLop half (Part B) of the design in
`docs/superpowers/specs/2026-06-26-plot-api-misuse-hardening-design.md`. The
companion root fix (function graphs auto-sizing to data) lives in the
SciQLopPlots repo (`docs/superpowers/plans/2026-06-26-function-graph-auto-size.md`
there). Part B is additive and ships independently; the docstring claim that
`labels` is optional for multi-component callbacks only becomes true once the
SciQLopPlots pin is bumped to the release containing that fix.

---

## File Structure

- `SciQLop/user_api/plot/_graphs.py` — home for `_UNSET` + `_with_explicit` (low-level plumbing, already hosts `ensure_arrays_of_double`; imported by both `_panel.py` and `_plots.py`, no circular import).
- `SciQLop/user_api/plot/_panel.py` — promote params + docstrings on `plot_function`, `plot_data`, `plot_product`; full docstring on `plot`.
- `SciQLop/user_api/plot/_plots.py` — promote params + docstrings on `XYPlot.plot`, `TimeSeriesPlot.plot`, `scatter`.
- `tests/test_plot_kwargs_hardening.py` — new test module.

**Why `_graphs.py` for the helper:** `_panel.py` imports from `_plots.py` and `_plots.py` imports from `_graphs.py`, so `_graphs.py` is the lowest common module both can import without a cycle.

**Promotion matrix** (keyword-only, sentinel-forwarded):

| Method | Promoted params |
|---|---|
| `plot_function` | `labels, name, plot_type, graph_type, colors, y_log_scale, z_log_scale` (+ `f.__name__` naming hint) |
| `plot_data` | `labels, name, plot_type, graph_type, colors, y_log_scale, z_log_scale` |
| `plot_product` | `plot_type, graph_type` only — provider supplies labels/name/scales; promoting them would collide with the explicit kwargs the spectrogram path already passes to `target.plot` |
| `plot` (omnibus) | none — full docstring only; it dispatches by arg type and forwards `**kwargs` to the typed methods |
| `XYPlot.plot`, `TimeSeriesPlot.plot` | `labels, name, colors, graph_type, y_log_scale, z_log_scale` (keep existing `y_axis` handling) |
| `scatter` | `labels, name, colors` (keep existing `marker`, `y_axis` handling) |

---

### Task 1: `_UNSET` sentinel + `_with_explicit` helper

**Files:**
- Modify: `SciQLop/user_api/plot/_graphs.py`
- Test: `tests/test_plot_kwargs_hardening.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plot_kwargs_hardening.py`:

```python
"""Backward-compatible promotion of plot **kwargs to explicit keyword params."""
import numpy as np
import pytest
from .fixtures import *

from SciQLop.user_api.plot._graphs import _UNSET, _with_explicit


def test_with_explicit_forwards_set_values():
    kwargs = {"existing": 1}
    out = _with_explicit(kwargs, labels=["a", "b"], name="g")
    assert out is kwargs                      # mutates and returns the same dict
    assert out == {"existing": 1, "labels": ["a", "b"], "name": "g"}


def test_with_explicit_skips_unset_values():
    out = _with_explicit({}, labels=_UNSET, name="g", colors=_UNSET)
    assert out == {"name": "g"}               # _UNSET params are not forwarded


def test_with_explicit_unset_is_falsy_safe():
    # A real value that is falsy (False / [] / 0) must still be forwarded.
    out = _with_explicit({}, y_log_scale=False, labels=[], graph_type=0)
    assert out == {"y_log_scale": False, "labels": [], "graph_type": 0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -v --no-xvfb`
Expected: FAIL with `ImportError: cannot import name '_UNSET'`.

- [ ] **Step 3: Write minimal implementation**

In `SciQLop/user_api/plot/_graphs.py`, after the imports / near `ensure_arrays_of_double`, add:

```python
_UNSET = object()


def _with_explicit(kwargs: dict, **named) -> dict:
    """Fold caller-set keyword params into the forwarded ``kwargs`` dict.

    Values left as the ``_UNSET`` sentinel are not inserted, preserving the
    exact present/absent semantics the ``**kwargs`` passthrough had before
    these options were promoted to explicit keyword parameters. Falsy real
    values (``False``, ``[]``, ``0``) are forwarded; only ``_UNSET`` is skipped.
    """
    for key, value in named.items():
        if value is not _UNSET:
            kwargs[key] = value
    return kwargs
```

Add `'_UNSET'` and `'_with_explicit'` are module-private (leading underscore) — do not add to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -v --no-xvfb`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/user_api/plot/_graphs.py tests/test_plot_kwargs_hardening.py
git commit -m "feat(user_api): add _with_explicit sentinel forwarding helper"
```

---

### Task 2: Promote `plot_function` params + `f.__name__` naming hint

**Files:**
- Modify: `SciQLop/user_api/plot/_panel.py:217-223` (`plot_function`)
- Test: `tests/test_plot_kwargs_hardening.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plot_kwargs_hardening.py`:

```python
def _capture_panel_fn(monkeypatch, attr):
    """Spy that records the kwargs reaching a component-layer plot function
    and still delegates to the real one (so the graph is really created)."""
    import SciQLop.user_api.plot._panel as pm
    captured = {}
    original = getattr(pm, attr)

    def spy(impl, *args, **kwargs):
        captured.clear()
        captured.update(kwargs)
        return original(impl, *args, **kwargs)

    monkeypatch.setattr(pm, attr, spy)
    return captured


def test_plot_function_forwards_set_params_only(plot_panel, monkeypatch):
    captured = _capture_panel_fn(monkeypatch, "_plot_function")

    def f(start, stop):
        x = np.linspace(start, stop, 10)
        return x, np.sin(x)

    plot_panel.plot_function(f, labels=["s"], y_log_scale=True)
    assert captured["labels"] == ["s"]
    assert captured["y_log_scale"] is True
    assert "colors" not in captured            # omitted → not forwarded


def test_plot_function_name_hint_from_function_name(plot_panel, monkeypatch):
    captured = _capture_panel_fn(monkeypatch, "_plot_function")

    def my_signal(start, stop):
        x = np.linspace(start, stop, 10)
        return x, np.sin(x)

    plot_panel.plot_function(my_signal)
    assert captured["name"] == "my_signal"     # base name hint applied

    captured2 = _capture_panel_fn(monkeypatch, "_plot_function")
    plot_panel.plot_function(lambda s, e: (np.array([s, e]), np.array([0.0, 1.0])))
    assert "name" not in captured2             # <lambda> is skipped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k plot_function -v --no-xvfb`
Expected: FAIL — `name`/`labels` land nowhere distinguishable (today they pass through `**kwargs` so `labels` is present, but `name` hint is absent → `KeyError: 'name'`).

- [ ] **Step 3: Write minimal implementation**

Replace `plot_function` in `SciQLop/user_api/plot/_panel.py`. Update the import at the top of the file (the line `from ._graphs import (ensure_arrays_of_double, ...)`) to also import `_UNSET, _with_explicit`:

```python
from ._graphs import (ensure_arrays_of_double, Histogram2D, _create_histogram2d,
                      validate_histogram_bins as _validate_histogram_bins,
                      _UNSET, _with_explicit)
```

Then:

```python
    @on_main_thread
    @_tracing.traced("PlotPanel.plot_function", cat="plot")
    def plot_function(self, f, plot_index=-1, *, labels=_UNSET, name=_UNSET,
                      plot_type=_UNSET, graph_type=_UNSET, colors=_UNSET,
                      y_log_scale=_UNSET, z_log_scale=_UNSET, **kwargs) -> Tuple[
            ProjectionPlot | TimeSeriesPlot, Plottable]:
        """Plot a callback ``f(start, stop) -> (x, y[, z])`` that is re-evaluated
        whenever the panel's time range changes.

        Parameters
        ----------
        f : callable
            ``f(start, stop)`` returning ``(x, y)`` for a line/scatter/curve or
            ``(x, y, z)`` for a colormap. ``start``/``stop`` are epoch seconds.
        plot_index : int
            Existing subplot to draw into. -1 (or out of range) appends a new one.
        labels : list[str], optional
            Per-component names shown in the legend. For callbacks the *number*
            of lines is detected from the data, so labels are cosmetic; if
            omitted, components are auto-named from the callback's name.
        name : str, optional
            Graph name. Defaults to ``f.__name__`` (used as the base for
            auto-generated component names) unless ``f`` is a lambda.
        plot_type : PlotType, optional
            TimeSeries (default), Projection or XY.
        graph_type : GraphType, optional
            Line (default), Curve, ColorMap or Scatter.
        colors : list, optional
            Per-component colors; defaults to the panel palette.
        y_log_scale, z_log_scale : bool, optional
            Use a logarithmic Y / Z (colormap) scale.
        **kwargs
            Forwarded to SciQLopPlots (e.g. ``gradient`` for colormaps).

        Returns
        -------
        Tuple[ProjectionPlot | TimeSeriesPlot, Plottable]
        """
        kwargs = _with_explicit(kwargs, labels=labels, name=name,
                                plot_type=plot_type, graph_type=graph_type,
                                colors=colors, y_log_scale=y_log_scale,
                                z_log_scale=z_log_scale)
        if name is _UNSET and labels is _UNSET:
            hint = getattr(f, "__name__", None)
            if hint and hint != "<lambda>":
                kwargs["name"] = hint
        kwargs = _normalize_plot_kwargs(kwargs)
        _p, _g = _plot_function(self._get_impl_or_raise(), f, index=plot_index, **kwargs)
        wrapped_plot = to_plot(_p)
        return wrapped_plot, to_plottable(_g, plot=wrapped_plot)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k plot_function -v --no-xvfb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/user_api/plot/_panel.py tests/test_plot_kwargs_hardening.py
git commit -m "feat(user_api): explicit params + name hint on plot_function"
```

---

### Task 3: Promote `plot_data` params

**Files:**
- Modify: `SciQLop/user_api/plot/_panel.py:177-215` (`plot_data`)
- Test: `tests/test_plot_kwargs_hardening.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_plot_data_forwards_set_params_only(plot_panel, monkeypatch):
    captured = _capture_panel_fn(monkeypatch, "_plot_static_data")
    x = np.linspace(0, 1, 20)
    y = np.column_stack([np.sin(x), np.cos(x)])
    plot_panel.plot_data(x, y, labels=["a", "b"], colors=["#ff0000", "#00ff00"])
    assert captured["labels"] == ["a", "b"]
    assert captured["colors"] == ["#ff0000", "#00ff00"]
    assert "y_log_scale" not in captured
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k plot_data -v --no-xvfb`
Expected: FAIL — `_plot_static_data` is the spied name but the existing call already forwards `labels`/`colors` via `**kwargs`, so this passes for those keys; the assertion `"y_log_scale" not in captured` already holds. The *failing* part is that without the signature change there is nothing to verify keyword-only promotion. To make the test meaningfully red, add this line which fails today because `plot_data` accepts the param only via `**kwargs` (works) — instead assert the keyword-only contract:

```python
def test_plot_data_params_are_keyword_only(plot_panel):
    x = np.linspace(0, 1, 20)
    y = np.sin(x)
    with pytest.raises(TypeError):
        # labels must be keyword-only; positional after plot_index is rejected
        plot_panel.plot_data(x, y, -1, ["a"])
```

Expected: FAIL today (the 4th positional currently lands in `**kwargs`-free signature as an error already? No — current signature is `plot_data(self, x, y=None, z=None, plot_index=-1, **kwargs)`, so `plot_data(x, y, -1, ["a"])` binds `z=-1`, `plot_index=["a"]` → no TypeError). So this raises only after we add the keyword-only `*`.

- [ ] **Step 3: Write minimal implementation**

Replace the `plot_data` signature and prepend the forwarding line. Keep the existing body (SpeasyVariable handling + `_normalize_plot_kwargs` + `_plot_static_data`) unchanged below it:

```python
    @on_main_thread
    @_tracing.traced("PlotPanel.plot_data", cat="plot")
    def plot_data(self, x, y=None, z=None, plot_index=-1, *, labels=_UNSET,
                  name=_UNSET, plot_type=_UNSET, graph_type=_UNSET, colors=_UNSET,
                  y_log_scale=_UNSET, z_log_scale=_UNSET, **kwargs) -> Tuple[
            ProjectionPlot | TimeSeriesPlot, Plottable]:
        """Plot static data or a SpeasyVariable in the panel.

        Parameters
        ----------
        x : array-like or SpeasyVariable
            X data, or a SpeasyVariable (time + values extracted automatically).
        y : array-like, optional
            Y data. Not needed if ``x`` is a SpeasyVariable. A 2-D ``y`` draws
            one line per column.
        z : array-like, optional
            2-D Z data ``[len(x), len(y)]`` → builds a colormap.
        plot_index : int
            Existing subplot to draw into. -1 (or out of range) appends a new one.
        labels : list[str], optional
            Per-component legend names.
        name : str, optional
            Graph name.
        plot_type : PlotType, optional
            TimeSeries (default), Projection or XY.
        graph_type : GraphType, optional
            Line (default), Curve, ColorMap or Scatter.
        colors : list, optional
            Per-component colors; defaults to the panel palette.
        y_log_scale, z_log_scale : bool, optional
            Use a logarithmic Y / Z scale.
        **kwargs
            Forwarded to SciQLopPlots.

        Returns
        -------
        Tuple[ProjectionPlot | TimeSeriesPlot, Plottable]
        """
        kwargs = _with_explicit(kwargs, labels=labels, name=name,
                                plot_type=plot_type, graph_type=graph_type,
                                colors=colors, y_log_scale=y_log_scale,
                                z_log_scale=z_log_scale)
        if isinstance(x, _SpeasyVariable):
            arrays = _speasy_variable_to_arrays(x)
            x, y = arrays[0], arrays[1]
            z = arrays[2] if len(arrays) == 3 else None
        elif y is None:
            raise ValueError(
                "y data is required unless x is a SpeasyVariable")

        kwargs = _normalize_plot_kwargs(kwargs)
        _p, _g = _plot_static_data(self._get_impl_or_raise(), *ensure_arrays_of_double(x, y, z), index=plot_index,
                                   **kwargs)
        wrapped_plot = to_plot(_p)
        return wrapped_plot, to_plottable(_g, plot=wrapped_plot)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k plot_data -v --no-xvfb`
Expected: PASS (both `plot_data` tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/user_api/plot/_panel.py tests/test_plot_kwargs_hardening.py
git commit -m "feat(user_api): explicit keyword-only params on plot_data"
```

---

### Task 4: Promote `plot_product` `plot_type`/`graph_type`

**Files:**
- Modify: `SciQLop/user_api/plot/_panel.py:149-175` (`plot_product`)
- Test: `tests/test_plot_kwargs_hardening.py`

- [ ] **Step 1: Write the failing test**

Append (uses the speasy provider already wired in the test app; if no provider is available in CI, mark with the project's existing speasy marker — check a sibling test such as `tests/test_plot_scatter_hline.py` for the pattern):

```python
def test_plot_product_keyword_only_and_backward_compatible(plot_panel):
    from SciQLop.user_api.plot import PlotType
    # plot_type must remain accepted by keyword (existing call sites)
    with pytest.raises(TypeError):
        plot_panel.plot_product(["a", "b"], -1, PlotType.XY)  # keyword-only now
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k plot_product -v --no-xvfb`
Expected: FAIL — today the 3rd positional binds into the old signature without error.

- [ ] **Step 3: Write minimal implementation**

Replace the `plot_product` signature and prepend forwarding; keep the body:

```python
    @on_main_thread
    @_tracing.traced("PlotPanel.plot_product", cat="plot")
    def plot_product(self, product: AnyProductType, plot_index=-1, *,
                     plot_type=_UNSET, graph_type=_UNSET, **kwargs) -> Tuple[
            ProjectionPlot | TimeSeriesPlot, Plottable]:
        """Plot a product in the panel.

        Parameters
        ----------
        product : AnyProductType
            A product path: ``str``, list of ``str``, or a ``VirtualProduct``.
        plot_index : int
            Existing subplot to draw into. -1 (or out of range) appends a new one.
        plot_type : PlotType, optional
            TimeSeries (default), Projection or XY.
        graph_type : GraphType, optional
            Line (default), Curve, ColorMap or Scatter.
        **kwargs
            Forwarded to SciQLopPlots. Note: component labels, the graph name
            and log scales are supplied by the product's provider, so passing
            them here is unsupported for products.

        Returns
        -------
        Tuple[ProjectionPlot | TimeSeriesPlot, Plottable]
        """
        kwargs = _with_explicit(kwargs, plot_type=plot_type, graph_type=graph_type)
        kwargs = _normalize_plot_kwargs(kwargs)
        _p, _g = plot_product_or_raise(self._get_impl_or_raise(), product, index=plot_index, **kwargs)
        wrapped_plot = to_plot(_p)
        return wrapped_plot, to_plottable(_g, plot=wrapped_plot)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k plot_product -v --no-xvfb`
Expected: PASS.

- [ ] **Step 5: Run the existing plot suite to confirm no regression**

Run: `uv run pytest tests/test_plot_scatter_hline.py tests/test_plot_y2_axis.py tests/test_overlay.py -v --no-xvfb`
Expected: PASS (these call `plot_data`/`plot_product` with keyword `plot_type=`/`graph_type=`).

- [ ] **Step 6: Commit**

```bash
git add SciQLop/user_api/plot/_panel.py tests/test_plot_kwargs_hardening.py
git commit -m "feat(user_api): explicit plot_type/graph_type on plot_product"
```

---

### Task 5: Full docstring on the `plot()` omnibus

**Files:**
- Modify: `SciQLop/user_api/plot/_panel.py:309-327` (`plot`)
- Test: `tests/test_plot_kwargs_hardening.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_plot_omnibus_still_dispatches_and_forwards(plot_panel, monkeypatch):
    captured = _capture_panel_fn(monkeypatch, "_plot_function")

    def f(start, stop):
        x = np.linspace(start, stop, 10)
        return x, np.sin(x)

    plot_panel.plot(f, labels=["s"])           # routes to plot_function
    assert captured["labels"] == ["s"]


def test_plot_has_docstring():
    assert (PlotPanel.plot.__doc__ or "").strip(), "plot() must document its options"
```

(Add `from SciQLop.user_api.plot import PlotPanel` to the test module imports.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k omnibus_or_docstring -v --no-xvfb`
Run: `uv run pytest "tests/test_plot_kwargs_hardening.py::test_plot_has_docstring" -v --no-xvfb`
Expected: `test_plot_has_docstring` FAILS (no docstring today).

- [ ] **Step 3: Write minimal implementation**

Add a docstring to `plot` (signature unchanged — it stays `*args, plot_index=-1, **kwargs`):

```python
    @on_main_thread
    def plot(self, *args, plot_index=-1, **kwargs) -> Tuple[ProjectionPlot | TimeSeriesPlot, Plottable] | None:
        """Omnibus plotting entry point — dispatches on argument type.

        Accepts, and forwards ``**kwargs`` to the matching typed method:

        - ``plot(speasy_variable, ...)``         → :meth:`plot_data`
        - ``plot(product, ...)``                 → :meth:`plot_product`
          (``str`` / list of ``str`` / ``VirtualProduct``)
        - ``plot(callable, ...)``                → :meth:`plot_function`
        - ``plot(x, y[, z], ...)``               → :meth:`plot_data`

        For documented, discoverable options (``labels``, ``name``,
        ``plot_type``, ``graph_type``, ``colors``, ``y_log_scale``,
        ``z_log_scale``) prefer the typed methods — they list these in their
        signatures. Any of them may also be passed here as keyword arguments
        and are forwarded unchanged.

        Returns
        -------
        Tuple[Plot, Plottable] or None
        """
        if len(args) == 1 and isinstance(args[0], _SpeasyVariable):
            return self.plot_data(args[0], plot_index=plot_index, **kwargs)
        if len(args) <= 1:  # product or callable
            product = _maybe_product(*args, **kwargs)
            if product is not Nothing:
                kwargs.pop("product", None)
                return self.plot_product(product.value, plot_index, **kwargs)
            callback = _maybe_callable(*args, **kwargs)
            if callback is not Nothing:
                kwargs.pop("callback", None)
                return self.plot_function(callback.value, plot_index, **kwargs)
            raise ValueError(
                "plot() could not interpret its arguments: expected a product "
                "path (str, list of str or VirtualProduct), a callable "
                "f(start, stop), a SpeasyVariable, or data arrays (x, y[, z])")
        # static data plot (x, y, [z])
        return self.plot_data(*args, plot_index=plot_index, **kwargs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k "omnibus or docstring" -v --no-xvfb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/user_api/plot/_panel.py tests/test_plot_kwargs_hardening.py
git commit -m "docs(user_api): document plot() omnibus options"
```

---

### Task 6: Promote params on `XYPlot.plot` and `TimeSeriesPlot.plot`

**Files:**
- Modify: `SciQLop/user_api/plot/_plots.py:394-418` (`XYPlot.plot`), `SciQLop/user_api/plot/_plots.py:533-575` (`TimeSeriesPlot.plot`)
- Test: `tests/test_plot_kwargs_hardening.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_plot_level_methods_are_keyword_only(plot_panel):
    x = np.linspace(0, 1, 20)
    y = np.sin(x)
    plot, _g = plot_panel.plot_data(x, y)      # a TimeSeriesPlot
    with pytest.raises(TypeError):
        plot.plot(x, y, ["a"])                 # labels must be keyword-only


def test_plot_level_name_is_observable(plot_panel):
    x = np.linspace(0, 1, 20)
    y = np.sin(x)
    plot, _g = plot_panel.plot_data(x, y)
    _p, graph = None, plot.plot(x, np.cos(x), name="second")
    assert graph._impl.name == "second"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k plot_level -v --no-xvfb`
Expected: FAIL — `plot.plot(x, y, ["a"])` does not raise today (`["a"]` lands as a 3rd positional → colormap path / ValueError, not TypeError), and `name` is not promoted.

- [ ] **Step 3: Write minimal implementation**

At the top of `_plots.py`, extend the existing `from ._graphs import ...` line to also import `_UNSET, _with_explicit`. Then update both methods. `XYPlot.plot`:

```python
    @on_main_thread
    def plot(self, *args, labels=_UNSET, name=_UNSET, colors=_UNSET,
             graph_type=_UNSET, y_log_scale=_UNSET, z_log_scale=_UNSET,
             y_axis="y", **kwargs):
        """Plot on this XY plot: two vectors ``(x, y)``, three ``(x, y, z)`` →
        colormap, or a callback ``f(start, stop) -> (x, y)``. Product paths are
        not accepted here — use ``PlotPanel.plot_product`` or
        ``TimeSeriesPlot.plot``.

        Parameters
        ----------
        labels : list[str], optional
            Per-component legend names.
        name : str, optional
            Graph name.
        colors : list, optional
            Per-component colors.
        graph_type : GraphType, optional
            Defaults to ``ParametricCurve`` for XY plots.
        y_log_scale, z_log_scale : bool, optional
            Logarithmic Y / Z scale.
        y_axis : {"y", "y2"}
            Bind the graph to the primary or secondary y-axis (line / curve /
            scatter only — not colormaps).
        **kwargs
            Forwarded to SciQLopPlots.
        """
        kwargs = _with_explicit(kwargs, labels=labels, name=name, colors=colors,
                                graph_type=graph_type, y_log_scale=y_log_scale,
                                z_log_scale=z_log_scale)
        kwargs["graph_type"] = kwargs.get("graph_type", _GraphType.ParametricCurve)
        if len(args) == 1:
            if callable(args[0]):
                return _bind_y_axis(Graph(self._get_impl_or_raise().plot(*args, **kwargs), plot=self), y_axis)
            else:
                raise ValueError("Invalid arguments")
        elif len(args) == 2:
            return _bind_y_axis(
                Graph(self._get_impl_or_raise().plot(*ensure_arrays_of_double(*args), **kwargs), plot=self),
                y_axis,
            )
        elif len(args) == 3:
            _reject_if_colormap_already_present(self._get_impl_or_raise())
            return ColorMap(self._get_impl_or_raise().plot(*ensure_arrays_of_double(*args), **kwargs))
        return None
```

`TimeSeriesPlot.plot` (note: a single non-callable arg is a product path — keep that branch; promoted params still forward harmlessly):

```python
    @on_main_thread
    def plot(self, *args, labels=_UNSET, name=_UNSET, colors=_UNSET,
             graph_type=_UNSET, y_log_scale=_UNSET, z_log_scale=_UNSET,
             y_axis="y", **kwargs):
        """Plot on this time-series plot: two/three vectors ``(x, y[, z])``, a
        product path, or a callback ``f(start, stop) -> (x, y[, z])``.

        Parameters
        ----------
        labels : list[str], optional
            Per-component legend names.
        name : str, optional
            Graph name.
        colors : list, optional
            Per-component colors.
        graph_type : GraphType, optional
            Line (default), Curve, ColorMap or Scatter.
        y_log_scale, z_log_scale : bool, optional
            Logarithmic Y / Z scale.
        y_axis : {"y", "y2"}
            Bind the graph to the primary or secondary y-axis.
        **kwargs
            Forwarded to SciQLopPlots.

        Returns
        -------
        Optional[Graph]
        """
        kwargs = _with_explicit(kwargs, labels=labels, name=name, colors=colors,
                                graph_type=graph_type, y_log_scale=y_log_scale,
                                z_log_scale=z_log_scale)
        if len(args) == 1:
            if callable(args[0]):
                return _bind_y_axis(to_plottable(self._get_impl_or_raise().plot(*args, **kwargs), plot=self), y_axis)
            else:
                return _bind_y_axis(
                    to_plottable(plot_product_or_raise(self._get_impl_or_raise(), args[0], **kwargs),
                                 plot=self),
                    y_axis,
                )
        elif 3 >= len(args) >= 2:
            if len(args) == 3:
                _reject_if_colormap_already_present(self._get_impl_or_raise())
            return _bind_y_axis(
                to_plottable(self._get_impl_or_raise().plot(*ensure_arrays_of_double(*args), **kwargs),
                             plot=self),
                y_axis,
            )
        raise ValueError("Invalid arguments")
```

Note: for the product-path branch (`TimeSeriesPlot.plot(product)`), promoted params still forward via `kwargs`; provider-supplied labels take precedence at the impl. Do not pass `labels` to a product call in tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k plot_level -v --no-xvfb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/user_api/plot/_plots.py tests/test_plot_kwargs_hardening.py
git commit -m "feat(user_api): explicit keyword-only params on plot-level plot()"
```

---

### Task 7: Promote params on `scatter`

**Files:**
- Modify: `SciQLop/user_api/plot/_plots.py:169-195` (`scatter`)
- Test: `tests/test_plot_kwargs_hardening.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_scatter_labels_observable(plot_panel):
    from SciQLop.user_api.plot import PlotType
    x = np.linspace(0, 1, 20)
    y = np.sin(x)
    plot, _g = plot_panel.plot_data(x, y, plot_type=PlotType.XY)
    g = plot.scatter(x, np.cos(x), labels=["pts"])
    assert g._impl.labels() == ["pts"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k scatter -v --no-xvfb`
Expected: today this likely PASSES (labels already forwarded via `**kwargs`). To create a red test for the keyword-only contract instead, use:

```python
def test_scatter_label_is_keyword_only(plot_panel):
    from SciQLop.user_api.plot import PlotType
    x = np.linspace(0, 1, 20)
    y = np.sin(x)
    plot, _g = plot_panel.plot_data(x, y, plot_type=PlotType.XY)
    with pytest.raises(TypeError):
        plot.scatter(x, np.cos(x), ["pts"])    # labels keyword-only
```

Expected: FAIL today (`scatter(x, y, **kwargs)` binds a 3rd positional? No — `scatter(self, x, y, **kwargs)` rejects a 3rd positional with TypeError already). If it already raises TypeError, keep only `test_scatter_labels_observable` as the meaningful assertion and skip the keyword-only test for `scatter`.

- [ ] **Step 3: Write minimal implementation**

```python
    @experimental_api()
    @on_main_thread
    def scatter(self, x, y, *, labels=_UNSET, name=_UNSET, colors=_UNSET,
                **kwargs) -> Graph:
        """Plot data as a scatter graph (markers only, no lines).

        Parameters
        ----------
        x, y : array-like
            Data arrays. Converted to float64 automatically.
        labels : list[str], optional
            Per-component legend names.
        name : str, optional
            Graph name.
        colors : list, optional
            Per-component colors.
        **kwargs
            Forwarded to SciQLopPlots (e.g. ``marker``, ``y_axis``).

        Returns
        -------
        Graph
            The created scatter graph.
        """
        kwargs = _with_explicit(kwargs, labels=labels, name=name, colors=colors)
        impl = self._get_impl_or_raise()
        kwargs.setdefault('marker', _GraphMarkerShape.FilledCircle)
        y_axis = kwargs.pop("y_axis", "y")
        graph = impl.scatter(*ensure_arrays_of_double(x, y), **kwargs)
        _fix_scatter_marker_pen(graph)
        wrapped = Graph(graph, plot=self)
        if y_axis != "y":
            wrapped.y_axis = y_axis
        return wrapped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plot_kwargs_hardening.py -k scatter -v --no-xvfb`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/user_api/plot/_plots.py tests/test_plot_kwargs_hardening.py
git commit -m "feat(user_api): explicit keyword-only params on scatter"
```

---

### Task 8: Full-module regression sweep

**Files:** none (verification only).

- [ ] **Step 1: Run the new module + the plot suite**

Run:
```bash
uv run pytest tests/test_plot_kwargs_hardening.py \
  tests/test_plot_scatter_hline.py tests/test_plot_y2_axis.py \
  tests/test_overlay.py tests/test_histogram2d.py \
  tests/test_plot_autoscale_percentile.py -v --no-xvfb
```
Expected: all PASS — confirms existing keyword call sites (`plot_type=`, `graph_type=`, `labels=`) are unaffected.

- [ ] **Step 2: Commit (no-op if clean)**

Nothing to commit; this task is a gate.

---

## Self-Review

**Spec coverage:**
- "Promote 7 options to explicit keyword-only params + docstrings across panel methods and per-plot mirrors" → Tasks 2–7. ✓
- "Sentinel forwarding preserves present/absent semantics" → Task 1 (`_with_explicit`) + Task 3 falsy-safe test. ✓
- "`plot_function` gains a docstring + `f.__name__` naming hint" → Task 2. ✓
- "`plot()` omnibus documented" → Task 5. ✓
- "Backward compatibility" → Task 4 step 5, Task 8 regression sweep, keyword-only `*` everywhere. ✓
- "Sequencing: labels-optional docstring depends on SciQLopPlots pin" → captured in the docstrings as "if omitted, components are auto-named" (true post-fix) and in the plan header scope note. The pin bump itself is a one-line `pyproject.toml` change tracked in the SciQLopPlots plan's handoff, not duplicated here.

**Placeholder scan:** none — every step has code/commands. The Task 4/7 tests include an explicit "if it already raises, keep the observable assertion" instruction because the keyword-only behavior of a 3-arg method depends on the existing signature; both branches are spelled out.

**Type/name consistency:** `_UNSET`, `_with_explicit` defined in Task 1 (`_graphs.py`) and imported identically in Tasks 2–7. Spy helper `_capture_panel_fn` defined once in Task 2, reused in Tasks 3 & 5. Component-layer spy targets (`_plot_function`, `_plot_static_data`) match the import names in `_panel.py`.

**Post-implementation doc sync (not a code task):** update the global reference `~/.claude/memory/sciqlop-user-api.md` so the promoted signatures are recorded (per the project rule that this file tracks user_api signature changes).
