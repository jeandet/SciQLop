# sciqlop_describe_product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `sciqlop_describe_product` agent tool that returns a normalized metadata description of a product (units, coverage, dims, fillval, labels) plus a raw-attribute passthrough, with an opt-in `probe=True` sample fetch for provider-uniform ground truth (real shape/fillval/frame/median cadence/NaN-gap fraction in the probed window).

**Architecture:** A new pure module `tools/describe.py` holds the metadata normalization, rendering, and orchestration, taking its resolver and probe-fetch backends as injected callables so the bulk is unit-tested offline with fake `ParameterIndex`/`SpeasyVariable` objects. `_builder.py` wires the real backends: identifier → `ParameterIndex` via `spz.inventories.flat_inventories` / the ProductsModel node's `speasy_id`, and the probe fetch via `speasy.get_data`. The tool is registered read-only (ungated) with `thread=True`.

**Tech Stack:** Python, speasy 1.7.1 (`spz.inventories.flat_inventories`, `ParameterIndex`, `SpeasyVariable`), numpy, matplotlib not needed here, pytest + pytest-qt.

## Global Constraints

- All commands run with `uv run`; canonical run `uv run pytest --no-xvfb <path> -q`.
- Tools are dicts `{name, description, input_schema, handler, gated?}` from `build_sciqlop_tools(main_window)` in `SciQLop/components/agents/tools/_builder.py`; handlers return `{"content": [{"type": "text", ...}]}`.
- `sciqlop_describe_product` is **read-only / ungated**, registered in the read-only `tools` list in `build_sciqlop_tools` (next to `_inspect_tool()`), with `thread=True` (inventory access / probe fetch do blocking I/O).
- Every test importing from `SciQLop.components.agents.tools.*` must take pytest-qt's `qtbot` fixture and import inside the test function (the agents package `__init__` → `chat_dock` → `_builder` → `ProductsModel` needs a `QApplication`). Do NOT edit `tests/conftest.py` or `tools/__init__.py`.
- speasy `ParameterIndex` attributes are provider-heterogeneous: CDA has `FILLVAL`, `spz_shape`, `LABL_PTR_1`, `CATDESC`, `UNITS`, `cdf_type`, `dataset`, `start_date`, `stop_date`; AMDA has `dim_1`/`dim_2`/`size`, `units`, `display_type`; SSC has `Resolution`, `ResourceId`. `spz_name`/`spz_uid`/`spz_provider` are METHODS (call them). Normalized fields are omitted when absent — no fake nulls.
- Reverse lookup: `spz.inventories.flat_inventories.<provider>.parameters[<spz_uid>]` → `ParameterIndex` (uid may itself contain `/`, e.g. `AC_H2_CRIS/cnt_Al`).
- speasy `SpeasyVariable` exposes `.values` (ndarray), `.time` (datetime64 ndarray), `.meta` (dict), `.fill_value`.
- Probe window: caller `start`/`stop` (ISO-8601 or POSIX seconds) if given, else a 24 h span ending at the index `stop_date`; if no window and no `stop_date`, skip the probe and note it. Probe reads coordinate frame from `var.meta` keys `COORDINATE_SYSTEM`/`coordinate_system`. Probe never raises — on error, return metadata-only + a `(probe failed: …)` note. Read-only; binds nothing.
- Auto-detect identifier: `//` in product → ProductsModel path; else speasy identifier (dotted inventory path OR `provider/uid`).

---

### Task 1: `tools/describe.py` — metadata normalization, rendering, orchestration (metadata-only path)

**Files:**
- Create: `SciQLop/components/agents/tools/describe.py`
- Test: `tests/test_agent_describe_product.py`

**Interfaces:**
- Produces:
  - `normalize(index) -> dict` — pulls normalized fields (`name, provider, uid, units, coverage, shape, fillval, labels, description`) from a `ParameterIndex`-like object; omits absent ones.
  - `raw_attrs(index, consumed: set) -> dict` — all non-underscore, non-callable instance attributes not already consumed, values stringified/trimmed.
  - `describe_product(product, *, probe=False, start=None, stop=None, resolve_index, probe_fetch) -> dict` — returns the `{"content":[...]}` payload. `resolve_index(product) -> (index, note)` and `probe_fetch(index, t0, t1) -> SpeasyVariable` are injected. (Task 1 wires only the metadata-only path; `probe` handling added in Task 2.)
- The injected `resolve_index(product)` returns `(index_or_None, note_or_None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_describe_product.py
class FakeIndex:
    """Stand-in for a speasy ParameterIndex. spz_* are methods; other
    attributes mimic raw provider metadata."""
    def __init__(self, name="", uid="", provider="", **attrs):
        self._name, self._uid, self._prov = name, uid, provider
        for k, v in attrs.items():
            setattr(self, k, v)

    def spz_name(self):
        return self._name

    def spz_uid(self):
        return self._uid

    def spz_provider(self):
        return self._prov


def _cda_index():
    return FakeIndex(
        name="cnt_Al", uid="AC_H2_CRIS/cnt_Al", provider="cda",
        UNITS="Counts/hour", FILLVAL=[-9.99e30], spz_shape=(7,),
        LABL_PTR_1=["cnt_Al 85.3-111.5", "cnt_Al 114.1-155.9"],
        CATDESC="Al counts at 7 energies", cdf_type="CDF_REAL4",
        dataset="AC_H2_CRIS", start_date="1997-08-27 00:00:00",
        stop_date="2026-06-11 23:00:00",
    )


def _amda_index():
    return FakeIndex(
        name="imf_gsm", uid="imf_gsm", provider="amda",
        units="nT", dim_1=1, dim_2=1, size=3, display_type="timeseries",
    )


def test_describe_cda_normalized_fields(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    out = describe_product(
        "cda/AC_H2_CRIS/cnt_Al", resolve_index=lambda p: (_cda_index(), None),
        probe_fetch=lambda *a: None)
    text = out["content"][0]["text"]
    assert "cnt_Al" in text and "cda" in text
    assert "Counts/hour" in text                 # units
    assert "-9.99e+30" in text or "-9.99e30" in text  # fillval surfaced
    assert "(7,)" in text                        # shape
    assert "2026-06-11" in text                  # coverage stop
    assert "cdf_type" in text                    # raw passthrough


def test_describe_amda_sparse_omits_absent_fields(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    out = describe_product(
        "amda/imf_gsm", resolve_index=lambda p: (_amda_index(), None),
        probe_fetch=lambda *a: None)
    text = out["content"][0]["text"]
    assert "imf_gsm" in text and "nT" in text
    assert "FILLVAL" not in text and "fillval" not in text.lower()  # absent → omitted
    assert "display_type" in text                # raw passthrough


def test_describe_unresolved_product_reports_cleanly(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    out = describe_product(
        "nope//bad", resolve_index=lambda p: (None, "product not found: nope//bad"),
        probe_fetch=lambda *a: None)
    assert "product not found" in out["content"][0]["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest --no-xvfb tests/test_agent_describe_product.py -q`
Expected: FAIL — `ModuleNotFoundError: ...tools.describe`.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/agents/tools/describe.py
"""Describe a product's metadata (read-only). Resolver and probe-fetch
backends are injected so this module is unit-tested offline."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple


def _call(index, attr):
    fn = getattr(index, attr, None)
    if fn is None:
        return None
    try:
        return fn() if callable(fn) else fn
    except Exception:
        return None


def _first(index, *names):
    for n in names:
        v = getattr(index, n, None)
        if v not in (None, ""):
            return n, v
    return None, None


def normalize(index) -> Dict[str, Any]:
    """Normalized fields + the set of raw attribute names they consumed."""
    fields: Dict[str, Any] = {}
    consumed = set()

    name = _call(index, "spz_name") or getattr(index, "name", None)
    if name:
        fields["name"] = name
    uid = _call(index, "spz_uid")
    if uid:
        fields["uid"] = uid
    provider = _call(index, "spz_provider")
    if provider:
        fields["provider"] = provider

    uk, uv = _first(index, "units", "UNITS")
    if uk:
        fields["units"] = uv
        consumed.add(uk)

    start = getattr(index, "start_date", None)
    stop = getattr(index, "stop_date", None)
    if start or stop:
        fields["coverage"] = {"start": start, "stop": stop}
        consumed.update({"start_date", "stop_date"})

    sk, sv = _first(index, "spz_shape")
    if sk:
        fields["shape"] = sv
        consumed.add(sk)
    else:
        dims = {d: getattr(index, d) for d in ("dim_1", "dim_2", "size")
                if getattr(index, d, None) is not None}
        if dims:
            fields["dims"] = dims
            consumed.update(dims)

    fk, fv = _first(index, "FILLVAL", "fillval")
    if fk:
        fields["fillval"] = fv
        consumed.add(fk)

    lk, lv = _first(index, "LABL_PTR_1", "components")
    if lk:
        fields["labels"] = lv
        consumed.add(lk)

    dk, dv = _first(index, "CATDESC", "description")
    if dk:
        fields["description"] = dv
        consumed.add(dk)

    return {"fields": fields, "consumed": consumed}


def raw_attrs(index, consumed: set) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in vars(index).items():
        if k.startswith("_") or k in consumed or callable(v):
            continue
        s = str(v)
        out[k] = s[:120] + ("…" if len(s) > 120 else "")
    return out


def _render(product: str, fields: Dict[str, Any], raw: Dict[str, str],
            probe: Optional[Dict[str, Any]] = None,
            note: Optional[str] = None) -> str:
    lines = [f"# `{product}`"]
    if note:
        lines.append(f"_{note}_")
    for key in ("name", "provider", "uid", "units", "shape", "dims",
                "fillval", "labels", "coverage", "description"):
        if key in fields:
            lines.append(f"- **{key}**: {fields[key]}")
    if probe:
        lines.append("\n## probe")
        for k, v in probe.items():
            lines.append(f"- **{k}**: {v}")
    if raw:
        lines.append("\n## raw metadata")
        for k, v in sorted(raw.items()):
            lines.append(f"- `{k}`: {v}")
    return "\n".join(lines)


def describe_product(product, *, probe: bool = False, start=None, stop=None,
                     resolve_index: Callable, probe_fetch: Callable) -> Dict[str, Any]:
    index, note = resolve_index(product)
    if index is None:
        return {"content": [{"type": "text", "text": note or f"could not resolve `{product}`"}]}
    norm = normalize(index)
    raw = raw_attrs(index, norm["consumed"])
    text = _render(product, norm["fields"], raw, probe=None, note=note)
    return {"content": [{"type": "text", "text": text}]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_agent_describe_product.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/describe.py tests/test_agent_describe_product.py
git commit -m "feat(agents): describe.py — product metadata normalization + rendering"
```

---

### Task 2: probe path (`probe=True`)

**Files:**
- Modify: `SciQLop/components/agents/tools/describe.py`
- Modify: `tests/test_agent_describe_product.py`

**Interfaces:**
- Consumes: `describe_product`, `FakeIndex`, `_cda_index` from Task 1.
- Produces: `probe_summary(var) -> dict` (real shape/fillval/frame/median-cadence/nan-gap); `describe_product` honours `probe=True` using injected `probe_fetch`, with the default-window rule and graceful failure.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np


class FakeVar:
    def __init__(self, values, times, meta=None, fill_value=None):
        self.values = np.asarray(values, dtype=float)
        self.time = np.asarray(times)
        self.meta = meta or {}
        self.fill_value = fill_value


def _sec_times(n, step_s=60):
    return (np.arange(n) * step_s).astype("datetime64[s]")


def test_probe_adds_real_shape_frame_and_gap_fraction(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    var = FakeVar([[1.0, 2.0, 3.0], [1.0, np.nan, 3.0]], _sec_times(2),
                  meta={"COORDINATE_SYSTEM": "gse"}, fill_value=-1e31)
    out = describe_product(
        "cda/AC_H2_CRIS/cnt_Al", probe=True, start=0, stop=120,
        resolve_index=lambda p: (_cda_index(), None),
        probe_fetch=lambda index, t0, t1: var)
    text = out["content"][0]["text"]
    assert "probe" in text
    assert "(2, 3)" in text            # real sampled shape
    assert "gse" in text               # coordinate frame from meta
    assert "-1e+31" in text or "-1e31" in text   # real fillval
    # one NaN of six values → ~16.7% gap
    assert "16.7" in text or "16.67" in text


def test_probe_default_window_used_when_no_start_stop(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    seen = {}

    def fetch(index, t0, t1):
        seen["t0"], seen["t1"] = t0, t1
        return FakeVar([1.0], _sec_times(1))

    describe_product(
        "cda/x", probe=True,
        resolve_index=lambda p: (_cda_index(), None),  # stop_date 2026-06-11 23:00:00
        probe_fetch=fetch)
    # default window is 24h ending at stop_date → 86400 s wide
    assert seen and (seen["t1"] - seen["t0"]) == 86400.0


def test_probe_failure_falls_back_to_metadata(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product

    def boom(index, t0, t1):
        raise ValueError("provider 502")

    out = describe_product(
        "cda/x", probe=True, start=0, stop=120,
        resolve_index=lambda p: (_cda_index(), None),
        probe_fetch=boom)
    text = out["content"][0]["text"]
    assert "probe failed" in text and "cnt_Al" in text   # metadata still present
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_agent_describe_product.py -k probe -q`
Expected: FAIL — probe fields absent (probe path not implemented yet).

- [ ] **Step 3: Write minimal implementation**

Add to `describe.py`:

```python
import numpy as np
import pandas as pd

_FRAME_KEYS = ("COORDINATE_SYSTEM", "coordinate_system", "FRAME", "frame")


def _to_epoch(x) -> float:
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    return pd.Timestamp(str(x)).timestamp()


def _default_window(index) -> Optional[Tuple[float, float]]:
    stop = getattr(index, "stop_date", None)
    if not stop:
        return None
    t1 = _to_epoch(stop)
    return (t1 - 86400.0, t1)


def probe_summary(var) -> Dict[str, Any]:
    vals = np.asarray(getattr(var, "values", []))
    info: Dict[str, Any] = {"sampled_shape": tuple(vals.shape)}
    fv = getattr(var, "fill_value", None)
    if fv is not None:
        info["fill_value"] = fv
    meta = getattr(var, "meta", {}) or {}
    for k in _FRAME_KEYS:
        if k in meta:
            info["frame"] = meta[k]
            break
    t = np.asarray(getattr(var, "time", []))
    if t.size >= 2:
        dt = np.median(np.diff(t).astype("timedelta64[ns]").astype(float)) / 1e9
        info["median_cadence_s"] = round(dt, 3)
    if vals.dtype.kind in "fiu" and vals.size:
        gap = 100.0 * (~np.isfinite(vals)).sum() / vals.size
        info["nan_gap_pct_in_window"] = round(gap, 1)
    return info
```

Then extend `describe_product` — replace its body's tail so `probe=True` fetches and augments:

```python
def describe_product(product, *, probe: bool = False, start=None, stop=None,
                     resolve_index: Callable, probe_fetch: Callable) -> Dict[str, Any]:
    index, note = resolve_index(product)
    if index is None:
        return {"content": [{"type": "text", "text": note or f"could not resolve `{product}`"}]}
    norm = normalize(index)
    raw = raw_attrs(index, norm["consumed"])

    probe_info = None
    if probe:
        if start is not None and stop is not None:
            window = (_to_epoch(start), _to_epoch(stop))
        else:
            window = _default_window(index)
        if window is None:
            note = (note + " " if note else "") + "(probe skipped: no window and no stop_date)"
        else:
            try:
                var = probe_fetch(index, window[0], window[1])
                probe_info = probe_summary(var)
            except Exception as e:  # noqa: BLE001
                note = (note + " " if note else "") + f"(probe failed: {type(e).__name__}: {e})"

    text = _render(product, norm["fields"], raw, probe=probe_info, note=note)
    return {"content": [{"type": "text", "text": text}]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_agent_describe_product.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/describe.py tests/test_agent_describe_product.py
git commit -m "feat(agents): describe probe=True — real shape/fillval/frame/gap in window"
```

---

### Task 3: wire `sciqlop_describe_product` into `_builder.py` + real resolver

**Files:**
- Modify: `SciQLop/components/agents/tools/_builder.py`
- Test: `tests/test_describe_tool_registration.py`

**Interfaces:**
- Consumes: `describe.describe_product`; `_kernel_manager` not needed (no kernel use).
- Produces: tool `sciqlop_describe_product` (ungated); `_resolve_index(product) -> (index, note)` inside `_describe_tool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_describe_tool_registration.py
"""sciqlop_describe_product registration + handler wiring (needs QApplication → qtbot)."""
from unittest.mock import MagicMock


def _tool(qtbot, name):
    import SciQLop.components.agents.tools._builder as builder
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_describe_tool_registered_ungated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_describe_product")
    assert t.get("gated", False) is False
    props = t["input_schema"]["properties"]
    assert props["product"]["type"] == "string"
    assert set(t["input_schema"]["required"]) == {"product"}
    for opt in ("probe", "start", "stop"):
        assert opt in props


def test_describe_handler_delegates(qtbot, monkeypatch):
    import asyncio
    import SciQLop.components.agents.tools.describe as describe
    captured = {}

    def fake_describe_product(product, *, probe, start, stop, resolve_index, probe_fetch):
        captured.update(product=product, probe=probe)
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(describe, "describe_product", fake_describe_product)
    out = asyncio.run(_tool(qtbot, "sciqlop_describe_product")["handler"](
        {"product": "cda/AC_H2_CRIS/cnt_Al", "probe": True}))
    assert out["content"][0]["text"] == "ok"
    assert captured["product"] == "cda/AC_H2_CRIS/cnt_Al" and captured["probe"] is True


def test_resolve_index_routes_speasy_uid(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    fake_index = object()

    class _Params(dict):
        pass

    class _Prov:
        parameters = {"AC_H2_CRIS/cnt_Al": fake_index}

    class _Flat:
        cda = _Prov()

    import speasy as spz
    monkeypatch.setattr(spz.inventories, "flat_inventories", _Flat(), raising=False)
    resolve = builder._make_resolve_index()
    index, note = resolve("cda/AC_H2_CRIS/cnt_Al")
    assert index is fake_index and note is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest --no-xvfb tests/test_describe_tool_registration.py -q`
Expected: FAIL — `StopIteration` / `AttributeError: _make_resolve_index`.

- [ ] **Step 3: Write minimal implementation**

In `_builder.py`, add a resolver factory and the tool factory, and register the tool in the read-only list.

Add the resolver factory (module level):

```python
def _make_resolve_index():
    """Resolve a product identifier to a speasy ParameterIndex.

    `//`-path → ProductsModel node → its speasy_id → flat-inventory lookup;
    otherwise a speasy identifier: a dotted inventory path, or `provider/uid`.
    Returns (index_or_None, note_or_None)."""
    def _flat_lookup(provider: str, uid: str):
        import speasy as spz
        prov = getattr(spz.inventories.flat_inventories, provider, None)
        params = getattr(prov, "parameters", None) if prov is not None else None
        if params and uid in params:
            return params[uid]
        return None

    def _from_speasy_id(spz_id: str):
        provider, _, uid = spz_id.partition("/")
        if uid:
            hit = _flat_lookup(provider, uid)
            if hit is not None:
                return hit
        # dotted inventory path fallback (e.g. cda.AC_H2_CRIS...)
        import speasy as spz
        node = spz.inventories.data_tree
        for part in spz_id.split("."):
            node = getattr(node, part, None)
            if node is None:
                return None
        return node

    def resolve(product: str):
        if "//" in product:
            from SciQLopPlots import ProductsModel
            node = ProductsModel.instance().node([p for p in product.split("//") if p])
            if node is None:
                return None, f"product not found: {product}"
            spz_id = node.metadata("speasy_id") if hasattr(node, "metadata") else None
            if spz_id:
                idx = _from_speasy_id(str(spz_id))
                if idx is not None:
                    return idx, None
            return node, "(describing ProductsModel node metadata; no speasy ParameterIndex found)"
        idx = _from_speasy_id(product)
        if idx is None:
            return None, f"product not found in speasy inventory: {product}"
        return idx, None

    return resolve


def _describe_tool() -> Dict[str, Any]:
    from . import describe

    def _probe_fetch(index, t0: float, t1: float):
        import speasy as spz
        uid = describe._call(index, "spz_uid")
        provider = describe._call(index, "spz_provider")
        spz_id = f"{provider}/{uid}" if provider and uid else (uid or "")
        return spz.get_data(spz_id, t0, t1)

    resolve_index = _make_resolve_index()

    def _run(payload: Dict[str, Any]) -> Any:
        return describe.describe_product(
            str(payload["product"]),
            probe=bool(payload.get("probe", False)),
            start=payload.get("start"), stop=payload.get("stop"),
            resolve_index=resolve_index, probe_fetch=_probe_fetch,
        )

    return _text_tool(
        "sciqlop_describe_product",
        (
            "Describe a product's metadata WITHOUT plotting/fetching it: units, "
            "time coverage, dimensionality, fill value, component labels, plus a "
            "raw-attribute dump. `product` is a `//`-path (from sciqlop_products_tree) "
            "or a speasy id (provider/uid or dotted inventory path) — auto-detected. "
            "Pass `probe=true` (with optional `start`/`stop`, ISO-8601 or POSIX seconds) "
            "to sample a small window and report the REAL shape, fill value, coordinate "
            "frame, median cadence and NaN-gap fraction within that window. Read-only. "
            "Call before sciqlop_fetch."
        ),
        {
            "type": "object",
            "properties": {
                "product": {"type": "string"},
                "probe": {"type": "boolean"},
                "start": {"type": ["string", "number"]},
                "stop": {"type": ["string", "number"]},
            },
            "required": ["product"],
        },
        _run,
        thread=True,  # inventory access / probe fetch block; keep off the GUI thread
    )
```

Register it in the read-only `tools` list in `build_sciqlop_tools`, right after `_inspect_tool(),`:

```python
        _inspect_tool(),
        _describe_tool(),
        _show_figure_tool(),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_describe_tool_registration.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/_builder.py tests/test_describe_tool_registration.py
git commit -m "feat(agents): register sciqlop_describe_product + inventory resolver"
```

---

### Task 4: suite sanity + gating check

**Files:** Test only (no source change unless a regression surfaces).

- [ ] **Step 1: Run the describe tests together**

Run: `uv run pytest --no-xvfb tests/test_agent_describe_product.py tests/test_describe_tool_registration.py -q`
Expected: PASS (9 total).

- [ ] **Step 2: Confirm the tool enumerates ungated**

Run:
```bash
QT_QPA_PLATFORM=offscreen uv run python - <<'PY'
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import SciQLop.components.agents.tools._builder as b
tools = {t["name"]: t.get("gated", False) for t in b.build_sciqlop_tools(MagicMock())}
assert tools.get("sciqlop_describe_product") is False, tools
print("OK: sciqlop_describe_product present, ungated. total tools:", len(tools))
PY
```
Expected: `OK: sciqlop_describe_product present, ungated. total tools: 28`

- [ ] **Step 3: Commit (only if fixups were needed)**

```bash
git add -A && git commit -m "test(agents): describe_product suite sanity"
```

## Self-Review

**Spec coverage:**
- Read-only/ungated tool, `thread=True`, read-only list → Task 3 + Task 4 gating check. ✅
- Auto-detect `//`-path vs speasy id → Task 3 `_make_resolve_index`. ✅
- Metadata-only normalized envelope + raw passthrough, absent fields omitted → Task 1 (`normalize`/`raw_attrs`/`_render`). ✅
- Provider heterogeneity (CDA rich vs AMDA sparse) → Task 1 tests cover both. ✅
- `probe=True` real shape/fillval/frame/median-cadence/NaN-gap in window → Task 2 (`probe_summary`). ✅
- Probe default window (24 h ending at stop_date), skip when no window+no stop_date, graceful failure → Task 2. ✅
- spz_uid → ParameterIndex reverse lookup via `flat_inventories` → Task 3 (`_flat_lookup`) + unit test. ✅
- `//`-path → ProductsModel node → speasy_id → lookup, with node-metadata fallback → Task 3 `resolve`. ⚠️ The ProductsModel branch is exercised at runtime, not unit-tested (needs a live model); the speasy-uid branch IS unit-tested. Acceptable; noted.
- Every agents.tools.* test takes `qtbot` and imports inside → all test snippets. ✅

**Placeholder scan:** No TBD/TODO; every code step is complete. ✅

**Type consistency:** `describe_product(product, *, probe, start, stop, resolve_index, probe_fetch)` identical across Tasks 1/2/3; `resolve_index` returns `(index, note)` everywhere; `probe_summary`/`normalize`/`raw_attrs` names consistent; `_call` reused by both `describe.py` and `_builder._probe_fetch`. ✅

**One noted gap:** the `//`-path→ProductsModel resolver branch has no offline unit test (the speasy-uid branch does). Runtime-exercised; a live-model integration test is a follow-up, not a blocker.
