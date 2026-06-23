"""Live kernel introspection for the agent: namespace listing + object inspect."""
from __future__ import annotations

import types
from typing import Any

_HIDDEN = {"In", "Out", "get_ipython", "exit", "quit", "open", "_", "__", "___",
           "_oh", "_dh", "_ih", "_sh"}
_MAX_VARS = 200
_MAX_REPR = 200


def _is_internal(name: str) -> bool:
    return name.startswith("_") or name in _HIDDEN


def _summary(value: Any) -> str:
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return f"ndarray{tuple(value.shape)} {value.dtype}"
    except Exception:
        pass
    try:
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            return f"DataFrame{tuple(value.shape)}"
    except Exception:
        pass
    if isinstance(value, (list, tuple, dict, set, str, bytes)):
        return f"len={len(value)} {type(value).__name__}"
    r = repr(value)
    return r[:_MAX_REPR] + ("…" if len(r) > _MAX_REPR else "")


def kernel_vars(shell) -> str:
    rows = []
    for name, value in list(shell.user_ns.items()):
        if _is_internal(name) or isinstance(value, types.ModuleType):
            continue
        rows.append(f"- `{name}`: {type(value).__name__} — {_summary(value)}")
        if len(rows) >= _MAX_VARS:
            break
    if not rows:
        return "kernel namespace is empty (no user variables)"
    return "# Kernel variables\n" + "\n".join(rows)


def inspect_name(shell, name: str) -> str:
    info = shell.object_inspect(name, detail_level=0)
    if not info.get("found"):
        return f"`{name}` is not defined in the kernel"
    out = [f"# `{name}`"]
    if info.get("type_name"):
        out.append(f"type: {info['type_name']}")
    if info.get("string_form"):
        out.append(f"value: {info['string_form'][:_MAX_REPR]}")
    if info.get("docstring"):
        out.append("\n" + info["docstring"][:1500])
    return "\n".join(out)
