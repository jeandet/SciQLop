# Agent fetch tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `sciqlop_fetch` (fetch products into the embedded kernel, return a handle + compact summary), truncate `sciqlop_exec_python` tracebacks, and add `sciqlop_show_figure` (return the current matplotlib figure).

**Architecture:** Three additions to the agent tool surface in `SciQLop/components/agents/tools/`. The fetch logic lives in a new pure module `tools/fetch.py` that takes its data backends (fetch-one, grid-interpolate) as injected callables, so the bulk is unit-tested offline with fake SpeasyVariables and a fake kernel namespace. `_builder.py` wires the real backends: `//`-paths resolve through the existing VP resolver (`dependencies._resolve_path`), bare ids go straight to `speasy.get_data`. Results bind into `km.shell.user_ns` (the shared kernel namespace).

**Tech Stack:** Python, speasy 1.7.1 (`SpeasyVariable`, `speasy.signal.resampling.interpolate`, `replace_fillval_by_nan`), numpy, pandas (cadence parsing), matplotlib (Agg, for previews/figures), pytest + pytest-qt.

## Global Constraints

- All commands run with `uv run` (e.g. `uv run pytest`). Local canonical run: `uv run pytest --no-xvfb`.
- Tools are dicts `{name, description, input_schema, handler, gated?}` returned from `build_sciqlop_tools(main_window)` in `SciQLop/components/agents/tools/_builder.py`. Handlers return `{"content": [{"type": "text"|"image", ...}]}`.
- `sciqlop_fetch` is **gated** (mutates the kernel namespace); `sciqlop_show_figure` is **read-only** (ungated). Traceback truncation modifies the existing gated `sciqlop_exec_python`.
- The shared kernel is reached via `_kernel_manager()` in `_builder.py`; its `.shell.user_ns` is the namespace, shared with JupyterLab. `km.submit_cell(code)` returns a `Future`.
- speasy `SpeasyVariable` exposes: `.name`, `.unit`, `.shape`, `.columns`, `.values` (ndarray), `.time` (ndarray), `.replace_fillval_by_nan(inplace=True, convert_to_float=True)`, `.to_dataframe()`.
- `speasy.signal.resampling.interpolate(ref, var)` interpolates `var` onto reference times `ref` (numpy datetime64 array) — this is the common-grid primitive.
- Importing `_builder` requires a `QApplication` (ProductsModel static), so registration/handler tests take pytest-qt's `qtbot` and import inside the test (see `tests/test_literature_tools.py`).
- Bind format: the chosen `name` holds a `dict[str, SpeasyVariable]` keyed by `var.name` (single product ⇒ 1-entry dict). Duplicate names get a `_2`, `_3`, … suffix.
- Resample method is linear only (via `interpolate`); alternate methods are out of scope.

---

### Task 1: `tools/fetch.py` — pure fetch/scrub/grid/bind/summary logic

**Files:**
- Create: `SciQLop/components/agents/tools/fetch.py`
- Test: `tests/test_agent_fetch_tool.py`

**Interfaces:**
- Produces:
  - `to_epoch(x: str | float) -> float` — ISO-8601 string or number → POSIX seconds.
  - `cadence_seconds(cadence: str) -> float` — e.g. `"1min"` → `60.0`.
  - `fetch_products(products, start, stop, name, shell_ns, *, cadence, overwrite, fetch_one, grid_interpolate) -> dict` — returns the `{"content": [...]}` tool payload and, on success, binds `shell_ns[name]`.
  - `fetch_one(product_id: str, t0: float, t1: float) -> list[SpeasyVariable]` is the injected backend contract (raises on failure).
  - `grid_interpolate(ref_times, var) -> SpeasyVariable` is the injected grid backend contract.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_fetch_tool.py
import numpy as np


class FakeVar:
    def __init__(self, name, values, times, unit="nT"):
        self.name = name
        self.values = np.asarray(values, dtype=float)
        self.time = np.asarray(times)
        self.unit = unit
        self.columns = [name] if self.values.ndim == 1 else [f"{name}{i}" for i in range(self.values.shape[1])]

    @property
    def shape(self):
        return self.values.shape

    def replace_fillval_by_nan(self, inplace=True, convert_to_float=True):
        return self

    def to_dataframe(self):  # only referenced by the bridges footer text
        import pandas as pd
        return pd.DataFrame(self.values)


def _times(n):
    return np.arange(n).astype("datetime64[s]")


def test_to_epoch_accepts_iso_and_number():
    from SciQLop.components.agents.tools.fetch import to_epoch
    assert to_epoch(100) == 100.0
    assert to_epoch("1970-01-01T00:01:40+00:00") == 100.0


def test_cadence_seconds():
    from SciQLop.components.agents.tools.fetch import cadence_seconds
    assert cadence_seconds("1min") == 60.0
    assert cadence_seconds("5s") == 5.0
    assert cadence_seconds("1h") == 3600.0


def test_fetch_single_binds_dict_and_summarizes():
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    var = FakeVar("B_gse", [1.0, 2.0, np.nan, 4.0], _times(4))
    out = fetch_products(
        ["amda/b_gse"], 0.0, 4.0, "BUILD", ns,
        cadence=None, overwrite=False,
        fetch_one=lambda pid, t0, t1: [var],
        grid_interpolate=lambda ref, v: v,
    )
    assert set(ns["BUILD"].keys()) == {"B_gse"}
    text = out["content"][0]["text"]
    assert "BUILD" in text and "B_gse" in text and "nT" in text
    assert "coverage 75" in text  # 3 of 4 finite
    assert "to_dataframe()" in text  # bridges footer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_fetch_tool.py -q --no-xvfb`
Expected: FAIL — `ModuleNotFoundError: ...tools.fetch`.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/agents/tools/fetch.py
"""Fetch products into the embedded kernel and return a handle + summary.

Pure logic: data backends (fetch-one, grid interpolation) are injected so this
module is unit-tested offline. `_builder` wires the real speasy/ProductsModel
backends.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

import numpy as np
import pandas as pd


def to_epoch(x) -> float:
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    return pd.Timestamp(str(x)).timestamp()


def cadence_seconds(cadence: str) -> float:
    return float(pd.Timedelta(cadence).total_seconds())


def _stats(var) -> str:
    vals = np.asarray(getattr(var, "values", []))
    if vals.dtype.kind not in "fiu" or vals.size == 0:
        return ""
    finite = np.isfinite(vals)
    coverage = 100.0 * finite.sum() / finite.size
    fills = int((~finite).sum())
    if finite.any():
        lo, mean, hi = np.nanmin(vals), np.nanmean(vals), np.nanmax(vals)
        rng = f", min/mean/max={lo:.3g}/{mean:.3g}/{hi:.3g}"
    else:
        rng = ""
    return f", coverage {coverage:.1f}%, fills {fills}{rng}"


def _var_line(short: str, var) -> str:
    unit = getattr(var, "unit", "") or ""
    return f"- `{short}` [{unit}] shape {tuple(getattr(var, 'shape', ()))}{_stats(var)}"


def _summary(name: str, mapping: Dict[str, Any], cadence, failures: List[str]) -> str:
    lines = [f"fetched into `{name}` — {len(mapping)} variable(s)"]
    if cadence:
        lines[0] += f", grid {cadence}"
    for short, var in mapping.items():
        lines.append(_var_line(short, var))
    for f in failures:
        lines.append(f"- ⚠️ {f}")
    if mapping:
        k = next(iter(mapping))
        lines.append(f"\nbridges: `{name}['{k}'].to_dataframe()`, `{name}['{k}'].values`, `.time`")
    return "\n".join(lines)


def _unique_key(mapping: Dict[str, Any], short: str) -> str:
    if short not in mapping:
        return short
    i = 2
    while f"{short}_{i}" in mapping:
        i += 1
    return f"{short}_{i}"


def fetch_products(products, start, stop, name, shell_ns, *, cadence, overwrite,
                   fetch_one: Callable, grid_interpolate: Callable) -> Dict[str, Any]:
    if not overwrite and name in shell_ns:
        existing = type(shell_ns[name]).__name__
        return {"content": [{"type": "text",
                "text": f"name `{name}` already bound (type {existing}); pass overwrite=True"}]}

    t0, t1 = to_epoch(start), to_epoch(stop)
    ref = None
    if cadence:
        dt = cadence_seconds(cadence)
        ref = np.arange(np.datetime64(int(t0 * 1e9), "ns"),
                        np.datetime64(int(t1 * 1e9), "ns"),
                        np.timedelta64(int(dt * 1e9), "ns"))

    mapping: Dict[str, Any] = {}
    failures: List[str] = []
    for pid in products:
        try:
            vars_ = fetch_one(pid, t0, t1)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{pid}: {type(e).__name__}: {e}")
            continue
        for var in vars_:
            var = var.replace_fillval_by_nan(inplace=True, convert_to_float=True)
            if ref is not None:
                var = grid_interpolate(ref, var)
            mapping[_unique_key(mapping, str(getattr(var, "name", pid)))] = var

    if mapping:
        shell_ns[name] = mapping
    return {"content": [{"type": "text", "text": _summary(name, mapping, cadence, failures)}]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_fetch_tool.py -q --no-xvfb`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/fetch.py tests/test_agent_fetch_tool.py
git commit -m "feat(agents): fetch.py — pure fetch/scrub/grid/bind/summary logic"
```

---

### Task 2: grid alignment + collision + partial-failure behavior

**Files:**
- Modify: `tests/test_agent_fetch_tool.py`
- (No source change expected — Task 1's `fetch_products` already implements these; this task pins the behavior with tests. If a test fails, fix `fetch.py` minimally.)

**Interfaces:**
- Consumes: `fetch_products`, `FakeVar`, `_times` from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
def test_cadence_aligns_all_products_on_shared_ref():
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    seen_refs = []

    def grid(ref, v):
        seen_refs.append(len(ref))
        return FakeVar(v.name, np.ones(len(ref)), ref)

    fetch_products(
        ["p1", "p2"], 0.0, 60.0, "G", ns,
        cadence="10s", overwrite=False,
        fetch_one=lambda pid, t0, t1: [FakeVar(pid, [1.0, 2.0], _times(2))],
        grid_interpolate=grid,
    )
    assert set(ns["G"].keys()) == {"p1", "p2"}
    assert seen_refs and len(set(seen_refs)) == 1        # every product hit the SAME grid
    assert ns["G"]["p1"].time.shape == ns["G"]["p2"].time.shape


def test_collision_without_overwrite_binds_nothing():
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {"X": 123}
    out = fetch_products(["p"], 0.0, 1.0, "X", ns, cadence=None, overwrite=False,
                         fetch_one=lambda *a: [FakeVar("p", [1.0], _times(1))],
                         grid_interpolate=lambda r, v: v)
    assert ns["X"] == 123                                # untouched
    assert "already bound" in out["content"][0]["text"]


def test_overwrite_true_rebinds():
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {"X": 123}
    fetch_products(["p"], 0.0, 1.0, "X", ns, cadence=None, overwrite=True,
                   fetch_one=lambda *a: [FakeVar("p", [1.0], _times(1))],
                   grid_interpolate=lambda r, v: v)
    assert isinstance(ns["X"], dict) and "p" in ns["X"]


def test_partial_failure_binds_good_reports_bad():
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}

    def fetch_one(pid, t0, t1):
        if pid == "bad":
            raise ValueError("product not found")
        return [FakeVar("good", [1.0], _times(1))]

    out = fetch_products(["good_id", "bad"], 0.0, 1.0, "M", ns, cadence=None,
                         overwrite=False, fetch_one=fetch_one, grid_interpolate=lambda r, v: v)
    assert "good" in ns["M"]
    assert "bad: ValueError: product not found" in out["content"][0]["text"]


def test_all_fail_binds_nothing():
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    out = fetch_products(["a", "b"], 0.0, 1.0, "M", ns, cadence=None, overwrite=False,
                         fetch_one=lambda *a: (_ for _ in ()).throw(ValueError("nope")),
                         grid_interpolate=lambda r, v: v)
    assert "M" not in ns
    assert out["content"][0]["text"].count("⚠️") == 2
```

- [ ] **Step 2: Run tests to verify they fail (or pass)**

Run: `uv run pytest tests/test_agent_fetch_tool.py -q --no-xvfb`
Expected: PASS if Task 1 is correct. If any FAIL, fix `fetch.py` minimally (do not change passing behavior).

- [ ] **Step 3: (only if needed) Fix `fetch.py`**

Adjust `fetch_products` so all five tests pass. No change anticipated.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_fetch_tool.py -q --no-xvfb`
Expected: PASS (8 tests total).

- [ ] **Step 5: Commit**

```bash
git add tests/test_agent_fetch_tool.py SciQLop/components/agents/tools/fetch.py
git commit -m "test(agents): pin fetch grid-alignment, collision, partial-failure"
```

---

### Task 3: `preview=True` thumbnail

**Files:**
- Modify: `SciQLop/components/agents/tools/fetch.py`
- Modify: `tests/test_agent_fetch_tool.py`

**Interfaces:**
- Produces: `render_preview(mapping: dict) -> bytes` (PNG) and a new `preview: bool = False` kwarg on `fetch_products` that appends `{"type": "image", "data": <b64>, "mimeType": "image/png"}` to the content list.

- [ ] **Step 1: Write the failing test**

```python
def test_preview_appends_image_block():
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    out = fetch_products(["p"], 0.0, 4.0, "P", ns, cadence=None, overwrite=False,
                         preview=True,
                         fetch_one=lambda *a: [FakeVar("B", [1.0, 2.0, 3.0, 4.0], _times(4))],
                         grid_interpolate=lambda r, v: v)
    kinds = [c["type"] for c in out["content"]]
    assert "image" in kinds
    img = next(c for c in out["content"] if c["type"] == "image")
    assert img["mimeType"] == "image/png" and img["data"]


def test_no_preview_by_default_is_text_only():
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    out = fetch_products(["p"], 0.0, 1.0, "P", ns, cadence=None, overwrite=False,
                         fetch_one=lambda *a: [FakeVar("B", [1.0], _times(1))],
                         grid_interpolate=lambda r, v: v)
    assert [c["type"] for c in out["content"]] == ["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_fetch_tool.py -k preview -q --no-xvfb`
Expected: FAIL — `fetch_products() got an unexpected keyword argument 'preview'`.

- [ ] **Step 3: Write minimal implementation**

Add to `fetch.py`:

```python
import base64


def render_preview(mapping: Dict[str, Any]) -> bytes:
    import io
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    n = max(1, len(mapping))
    fig = Figure(figsize=(6, 1.6 * n))
    for ax_i, (short, var) in enumerate(mapping.items(), start=1):
        ax = fig.add_subplot(n, 1, ax_i)
        vals = np.asarray(getattr(var, "values", []))
        t = np.asarray(getattr(var, "time", []))
        if vals.ndim <= 2 and vals.size and t.size == vals.shape[0]:
            ax.plot(t, vals)
        else:
            ax.text(0.5, 0.5, f"{short}: {tuple(vals.shape)} (preview skipped)",
                    ha="center", va="center")
        ax.set_ylabel(short)
    fig.tight_layout()
    buf = io.BytesIO()
    FigureCanvasAgg(fig).print_png(buf)
    return buf.getvalue()
```

Change `fetch_products` signature to `..., overwrite, preview=False, fetch_one, grid_interpolate)` and, just before the final `return`, when `mapping and preview`:

```python
    content = [{"type": "text", "text": _summary(name, mapping, cadence, failures)}]
    if mapping and preview:
        png = render_preview(mapping)
        content.append({"type": "image",
                        "data": base64.b64encode(png).decode("ascii"),
                        "mimeType": "image/png"})
    return {"content": content}
```

(Replace the previous single-item `return` with this `content` construction.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_fetch_tool.py -q --no-xvfb`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/fetch.py tests/test_agent_fetch_tool.py
git commit -m "feat(agents): fetch preview=True thumbnail (Agg, opt-in)"
```

---

### Task 4: wire `sciqlop_fetch` into `_builder.py` + public resolver

**Files:**
- Modify: `SciQLop/components/plotting/backend/dependencies.py` (add public `resolve_product_path`)
- Modify: `SciQLop/components/agents/tools/_builder.py` (register `_fetch_tool`)
- Test: `tests/test_fetch_tool_registration.py`

**Interfaces:**
- Consumes: `fetch.fetch_products`, `fetch.to_epoch`, `_kernel_manager()`, `dependencies.resolve_product_path`.
- Produces: tool `sciqlop_fetch` (gated), `dependencies.resolve_product_path(target, start, stop)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch_tool_registration.py
"""sciqlop_fetch registration + handler wiring (needs QApplication → qtbot)."""
import asyncio
from unittest.mock import MagicMock


def _tool(qtbot, name):
    import SciQLop.components.agents.tools._builder as builder
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_fetch_tool_registered_gated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_fetch")
    assert t.get("gated", False) is True
    props = t["input_schema"]["properties"]
    assert props["products"]["type"] == "array"
    assert set(t["input_schema"]["required"]) == {"products", "start", "stop", "name"}
    for opt in ("cadence", "overwrite", "preview"):
        assert opt in props


def test_fetch_handler_delegates_to_fetch_products(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    import SciQLop.components.agents.tools.fetch as fetch

    captured = {}

    def fake_fetch_products(products, start, stop, name, shell_ns, **kw):
        captured.update(products=products, name=name, kw=kw)
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(fetch, "fetch_products", fake_fetch_products)
    monkeypatch.setattr(builder, "_kernel_manager",
                        lambda: type("KM", (), {"shell": type("S", (), {"user_ns": {}})()})())

    out = asyncio.run(_tool(qtbot, "sciqlop_fetch")["handler"](
        {"products": ["speasy//amda//x"], "start": 0, "stop": 10, "name": "V",
         "cadence": "1min", "overwrite": True, "preview": False}))
    assert out["content"][0]["text"] == "ok"
    assert captured["name"] == "V" and captured["kw"]["cadence"] == "1min"


def test_fetch_handler_errors_without_kernel(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder, "_kernel_manager", lambda: None)
    out = asyncio.run(_tool(qtbot, "sciqlop_fetch")["handler"](
        {"products": ["x"], "start": 0, "stop": 1, "name": "V"}))
    assert "kernel is not available" in out["content"][0]["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetch_tool_registration.py -q --no-xvfb`
Expected: FAIL — `StopIteration` (no `sciqlop_fetch` tool registered).

- [ ] **Step 3: Write minimal implementation**

Add the public resolver to `SciQLop/components/plotting/backend/dependencies.py` (right after `_resolve_path`):

```python
def resolve_product_path(target, start: float, stop: float):
    """Public entry point: resolve a `//`-path (or list) to provider data,
    with no dependency pad. Reuses the VP dependency resolver."""
    return _resolve_path(target, start, stop)
```

In `_builder.py`, add a `_fetch_tool` factory and register it in `build_sciqlop_tools` (append to the read-only list is wrong — it is gated, so add it inside `_write_tools`'s returned list, next to `_exec_python_tool()`):

```python
def _fetch_tool() -> Dict[str, Any]:
    from . import fetch

    def _fetch_one(product_id: str, t0: float, t1: float):
        if "//" in product_id:
            from SciQLop.components.plotting.backend.dependencies import resolve_product_path
            data = resolve_product_path(product_id, t0, t1)
        else:
            import speasy as spz
            data = spz.get_data(product_id, t0, t1)
        if data is None:
            raise ValueError(f"no data for {product_id}")
        return list(data) if isinstance(data, (list, tuple)) else [data]

    def _grid(ref, var):
        from speasy.signal.resampling import interpolate
        return interpolate(ref, var)

    def _run(payload: Dict[str, Any]) -> Any:
        km = _kernel_manager()
        if km is None:
            return _error_content("embedded IPython kernel is not available")
        return fetch.fetch_products(
            [str(p) for p in payload["products"]],
            payload["start"], payload["stop"], str(payload["name"]),
            km.shell.user_ns,
            cadence=payload.get("cadence") or None,
            overwrite=bool(payload.get("overwrite", False)),
            preview=bool(payload.get("preview", False)),
            fetch_one=_fetch_one, grid_interpolate=_grid,
        )

    return _text_tool(
        "sciqlop_fetch",
        (
            "Fetch one or more products into the embedded kernel under `name` and "
            "return a compact summary (shape, units, coverage %, min/mean/max) — NOT "
            "the raw arrays. Compute on the handle afterwards with sciqlop_exec_python "
            "(e.g. `name['B_gse'].to_dataframe()`). `products` are `//`-paths "
            "(from sciqlop_products_tree) or speasy spz_uids — auto-detected. "
            "`start`/`stop` are ISO-8601 strings or POSIX seconds. With `cadence` "
            "(e.g. '1min') all products are fill-scrubbed and interpolated onto one "
            "common grid; without it they are bound at native cadence. Errors if "
            "`name` exists unless `overwrite=true`. `preview=true` adds a thumbnail."
        ),
        {
            "type": "object",
            "properties": {
                "products": {"type": "array", "items": {"type": "string"}},
                "start": {"type": ["string", "number"]},
                "stop": {"type": ["string", "number"]},
                "name": {"type": "string"},
                "cadence": {"type": "string"},
                "overwrite": {"type": "boolean"},
                "preview": {"type": "boolean"},
            },
            "required": ["products", "start", "stop", "name"],
        },
        _run,
        gated=True,
        thread=True,  # speasy fetch blocks; keep it off the GUI event loop
    )
```

Wire it into the gated list — change the `return` in `_write_tools`:

```python
    return [set_time_range, _create_panel_tool(main_window), _exec_python_tool(),
            _fetch_tool(), _install_package_tool()] + _notebook_write_tools() + [_run_notebook_cell_tool(), _interrupt_kernel_tool()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fetch_tool_registration.py -q --no-xvfb`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/_builder.py SciQLop/components/plotting/backend/dependencies.py tests/test_fetch_tool_registration.py
git commit -m "feat(agents): register sciqlop_fetch tool + public resolve_product_path"
```

---

### Task 5: `sciqlop_exec_python` traceback truncation

**Files:**
- Modify: `SciQLop/components/agents/tools/_builder.py` (`_format_exec_result` + new `_truncate_traceback`)
- Test: `tests/test_exec_traceback_truncation.py`

**Interfaces:**
- Produces: `_truncate_traceback(text: str, head: int = 20, tail: int = 20, max_lines: int = 60) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_exec_traceback_truncation.py
def test_short_traceback_unchanged():
    from SciQLop.components.agents.tools._builder import _truncate_traceback
    txt = "\n".join(f"line {i}" for i in range(10))
    assert _truncate_traceback(txt) == txt


def test_long_traceback_keeps_head_and_tail():
    from SciQLop.components.agents.tools._builder import _truncate_traceback
    txt = "\n".join(f"line {i}" for i in range(200))
    out = _truncate_traceback(txt)
    assert "line 0" in out            # head kept
    assert "line 199" in out          # tail (the actual exception) kept
    assert "line 100" not in out      # middle elided
    assert "elided" in out
    assert len(out.splitlines()) < 60


def test_format_exec_result_truncates_error(qtbot):
    from SciQLop.components.agents.tools._builder import _format_exec_result
    big = "\n".join(f"trace {i}" for i in range(200))
    out = _format_exec_result({"success": False, "error": big})
    assert "elided" in out and "trace 199" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_exec_traceback_truncation.py -q --no-xvfb`
Expected: FAIL — `ImportError: cannot import name '_truncate_traceback'`.

- [ ] **Step 3: Write minimal implementation**

In `_builder.py`, add near `_format_exec_result`:

```python
def _truncate_traceback(text: str, head: int = 20, tail: int = 20, max_lines: int = 60) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    omitted = len(lines) - head - tail
    return "\n".join(lines[:head] + [f"  … [{omitted} lines elided] …"] + lines[-tail:])
```

And in `_format_exec_result`, wrap the error line:

```python
    if not result.get("success") and result.get("error"):
        lines.append(f"error: {_truncate_traceback(str(result['error']))}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_exec_traceback_truncation.py -q --no-xvfb`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/_builder.py tests/test_exec_traceback_truncation.py
git commit -m "feat(agents): truncate long exec_python tracebacks (head+tail)"
```

---

### Task 6: `sciqlop_show_figure` tool

**Files:**
- Create: `SciQLop/components/agents/tools/figure.py`
- Modify: `SciQLop/components/agents/tools/_builder.py` (register `_show_figure_tool`, read-only)
- Test: `tests/test_show_figure_tool.py`

**Interfaces:**
- Produces: `figure.current_figure_png() -> bytes | None` (PNG of the current matplotlib figure, or `None` when there is none) and tool `sciqlop_show_figure` (ungated).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_show_figure_tool.py
import asyncio
from unittest.mock import MagicMock


def test_current_figure_png_none_when_no_figure():
    import matplotlib.pyplot as plt
    from SciQLop.components.agents.tools.figure import current_figure_png
    plt.close("all")
    assert current_figure_png() is None


def test_current_figure_png_returns_bytes_when_present():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from SciQLop.components.agents.tools.figure import current_figure_png
    plt.close("all")
    plt.figure(); plt.plot([0, 1, 2], [3, 1, 2])
    png = current_figure_png()
    plt.close("all")
    assert isinstance(png, (bytes, bytearray)) and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_show_figure_tool_registered_ungated(qtbot):
    import SciQLop.components.agents.tools._builder as builder
    t = next(x for x in builder.build_sciqlop_tools(MagicMock()) if x["name"] == "sciqlop_show_figure")
    assert t.get("gated", False) is False


def test_show_figure_handler_reports_when_no_figure(qtbot, monkeypatch):
    import matplotlib.pyplot as plt
    plt.close("all")
    import SciQLop.components.agents.tools._builder as builder
    t = next(x for x in builder.build_sciqlop_tools(MagicMock()) if x["name"] == "sciqlop_show_figure")
    out = asyncio.run(t["handler"]({}))
    assert "no active matplotlib figure" in out["content"][0]["text"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_show_figure_tool.py -q --no-xvfb`
Expected: FAIL — `ModuleNotFoundError: ...tools.figure`.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/agents/tools/figure.py
"""Return the current matplotlib figure from the embedded kernel as PNG.

The embedded kernel shares this process, so pyplot's global figure registry is
the same module singleton — no need to round-trip through the kernel.
"""
from __future__ import annotations

from typing import Optional


def current_figure_png() -> Optional[bytes]:
    import io
    import matplotlib.pyplot as plt
    if not plt.get_fignums():
        return None
    buf = io.BytesIO()
    plt.gcf().savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()
```

In `_builder.py`, add the factory and register it in the read-only list in `build_sciqlop_tools` (next to `_inspect_tool()`):

```python
def _show_figure_tool() -> Dict[str, Any]:
    import base64
    from . import figure

    def _run(_payload: Dict[str, Any]) -> Any:
        png = figure.current_figure_png()
        if png is None:
            return _error_content("no active matplotlib figure in the kernel")
        return {"content": [{"type": "image",
                             "data": base64.b64encode(png).decode("ascii"),
                             "mimeType": "image/png"}]}

    return _text_tool(
        "sciqlop_show_figure",
        (
            "Return the current matplotlib figure from the embedded kernel as a PNG. "
            "Use after plotting with matplotlib in sciqlop_exec_python. Read-only; "
            "reports cleanly when there is no active figure."
        ),
        {"type": "object", "properties": {}, "required": []},
        _run,
        thread=True,  # savefig does file/render work; keep off the GUI thread
    )
```

Add `_show_figure_tool(),` to the `tools` list in `build_sciqlop_tools` (after `_inspect_tool(),`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_show_figure_tool.py -q --no-xvfb`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/figure.py SciQLop/components/agents/tools/_builder.py tests/test_show_figure_tool.py
git commit -m "feat(agents): sciqlop_show_figure — return current matplotlib figure"
```

---

### Task 7: full-suite sanity + backend wrappers unaffected

**Files:**
- Test only (no source change unless a regression surfaces).

- [ ] **Step 1: Run the agent-tool tests together**

Run: `uv run pytest tests/test_agent_fetch_tool.py tests/test_fetch_tool_registration.py tests/test_exec_traceback_truncation.py tests/test_show_figure_tool.py tests/test_kernel_tools_registered.py tests/test_literature_tools.py -q --no-xvfb`
Expected: PASS (all).

- [ ] **Step 2: Confirm both backends still enumerate the new tools**

The Claude/Opencode backends wrap whatever `build_sciqlop_tools` returns, so no backend change is needed. Verify the three new tools appear and gating is right:

Run:
```bash
uv run python - <<'PY'
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import SciQLop.components.agents.tools._builder as b
tools = {t["name"]: t.get("gated", False) for t in b.build_sciqlop_tools(MagicMock())}
assert tools.get("sciqlop_fetch") is True, tools
assert tools.get("sciqlop_show_figure") is False, tools
assert "sciqlop_exec_python" in tools
print("OK:", {k: tools[k] for k in ("sciqlop_fetch", "sciqlop_show_figure", "sciqlop_exec_python")})
PY
```
Expected: `OK: {'sciqlop_fetch': True, 'sciqlop_show_figure': False, 'sciqlop_exec_python': True}`

- [ ] **Step 3: Commit (if any fixups were needed)**

```bash
git add -A && git commit -m "test(agents): full-suite sanity for fetch/figure/traceback tools"
```

## Self-Review

**Spec coverage:**
- `sciqlop_fetch` gated, handle+summary, no raw arrays → Tasks 1–4. ✅
- auto-detect `//`-path vs spz_uid → Task 4 `_fetch_one`. ✅
- optional cadence, fill-scrub + common-grid interpolate when given, raw otherwise → Tasks 1–3 (`fetch_products`, `interpolate`). ✅
- bind `dict[str, SpeasyVariable]` under chosen name, keyed by short-name with `_N` de-dup → Task 1 (`_unique_key`). ✅
- summary fields (units, shape, coverage %+gaps via fills, min/mean/max, bridges) → Task 1 (`_var_line`/`_stats`/`_summary`). *Gap ranges are summarized as fill count rather than explicit start/stop windows — acceptable for v1; explicit gap windows deferred (documented here).*
- `overwrite` collision behavior → Tasks 1–2. ✅
- `preview=True` opt-in thumbnail → Task 3. ✅
- partial success → Task 2. ✅
- traceback truncation head+tail → Task 5. ✅
- `sciqlop_show_figure` read-only → Task 6. ✅
- both backends wrap the list unchanged → Task 7. ✅

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✅

**Type consistency:** `fetch_products(..., fetch_one, grid_interpolate, preview)` signature consistent across Tasks 1/3/4; `FakeVar`/`_times` defined in Task 1 and reused; `_truncate_traceback` and `current_figure_png` signatures match their call sites. ✅

**One deviation from the spec, flagged:** the spec says coverage "with gap ranges"; the plan reports coverage % + fill (NaN) count instead of explicit gap start/stop windows. Explicit gap-window reporting is deferred as a small follow-up rather than blocking the slice.
