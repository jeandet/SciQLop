"""Fetch products into the embedded kernel and return a handle + summary.

Pure logic: data backends (fetch-one, grid interpolation) are injected so this
module is unit-tested offline. `_builder` wires the real speasy/ProductsModel
backends.
"""
from __future__ import annotations

import base64
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


def fetch_products(products, start, stop, name, shell_ns, *, cadence, overwrite,
                   preview=False, fetch_one: Callable, grid_interpolate: Callable) -> Dict[str, Any]:
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
            processed = []
            for var in vars_:
                var = var.replace_fillval_by_nan(inplace=True, convert_to_float=True)
                if ref is not None:
                    var = grid_interpolate(ref, var)
                processed.append(var)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{pid}: {type(e).__name__}: {e}")
            continue
        for var in processed:
            mapping[_unique_key(mapping, str(getattr(var, "name", pid)))] = var

    if mapping:
        shell_ns[name] = mapping
    content = [{"type": "text", "text": _summary(name, mapping, cadence, failures)}]
    if mapping and preview:
        png = render_preview(mapping)
        content.append({"type": "image",
                        "data": base64.b64encode(png).decode("ascii"),
                        "mimeType": "image/png"})
    return {"content": content}
