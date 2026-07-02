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
