"""Describe a product's metadata (read-only). Resolver and probe-fetch
backends are injected so this module is unit-tested offline."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np
import pandas as pd


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
    consumed.update({"name", "uid", "provider"})

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


def _median_cadence_seconds(t: np.ndarray) -> Optional[float]:
    if t.size < 2:
        return None
    diffs = np.diff(t)
    if diffs.dtype.kind == "m":  # timedelta64 (t was datetime64)
        seconds = diffs.astype("timedelta64[ns]").astype(float) / 1e9
    else:  # already numeric (e.g. epoch seconds)
        seconds = diffs.astype(float)
    return round(float(np.median(seconds)), 3)


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
    dt = _median_cadence_seconds(np.asarray(getattr(var, "time", [])))
    if dt is not None:
        info["median_cadence_s"] = dt
    if vals.dtype.kind in "fiu" and vals.size:
        gap = 100.0 * (~np.isfinite(vals)).sum() / vals.size
        info["nan_gap_pct_in_window"] = round(gap, 1)
    return info


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
