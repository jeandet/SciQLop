"""Ephemeris and coordinate-transform lookups via the CDPP 3DView REST API.

Pure logic: the HTTP GET is injected so this module is unit-tested offline.
`_builder.py` wires the real `speasy.core.http.get` client.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd

from speasy.core import http
from speasy.core.cache import CacheCall

BASE_URL = "https://3dview.irap.omp.eu/webresources"
_BODIES_AND_FRAMES_RETENTION = 7 * 24 * 3600  # 1 week — body/frame lists change rarely


def _to_epoch(x) -> float:
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    return pd.Timestamp(str(x)).timestamp()


def _epoch_to_3dview(t: float) -> str:
    return pd.Timestamp(t, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def _iso_to_ns(t: str) -> np.datetime64:
    return np.datetime64(t[:-1] if t.endswith("Z") else t, "ns")


def _check_overwrite(name: str, shell_ns: Dict[str, Any], overwrite: bool) -> Optional[Dict[str, Any]]:
    if not overwrite and name in shell_ns:
        existing = type(shell_ns[name]).__name__
        return {"content": [{"type": "text",
                "text": f"name `{name}` already bound (type {existing}); pass overwrite=True"}]}
    return None


def _time_range_params(start, stop, sampling) -> Dict[str, str]:
    params = {"format": "json",
              "start": _epoch_to_3dview(_to_epoch(start)),
              "stop": _epoch_to_3dview(_to_epoch(stop))}
    if sampling:
        params["sampling"] = str(int(sampling))
    return params


def render_bodies_and_frames(bodies_payload: Dict[str, Any], frames_payload: Dict[str, Any]) -> str:
    bodies = sorted(b["name"] for b in bodies_payload.get("bodies", []))
    frames = frames_payload.get("frames", [])
    lines = [f"### bodies ({len(bodies)})", ", ".join(bodies), "",
             f"### frames ({len(frames)})"]
    lines += [f"- `{f['name']}` — {f.get('desc', '')}" for f in frames]
    return "\n".join(lines)


def _bodies_and_frames_impl() -> str:
    bodies = http.get(f"{BASE_URL}/get_bodies", params={"format": "json"}).json()
    frames = http.get(f"{BASE_URL}/get_frames", params={"format": "json"}).json()
    return render_bodies_and_frames(bodies, frames)


bodies_and_frames = CacheCall(cache_retention=_BODIES_AND_FRAMES_RETENTION, is_pure=True)(_bodies_and_frames_impl)
