# Agent ephemeris & coordinate-transform tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `sciqlop_ephemeris`, `sciqlop_transform`, and `sciqlop_orbit_bodies_and_frames` agent tools, backed by the CDPP 3DView REST API, following the exact spec in `docs/superpowers/specs/2026-07-02-agent-ephemeris-transform-design.md`.

**Architecture:** A new pure-logic module `SciQLop/components/agents/tools/orbits.py` does JSON→`SpeasyVariable` parsing and kernel binding. `fetch_ephemeris`/`fetch_transform` follow `fetch.py`/`describe.py`'s convention of an injected `http_get: Callable` (fully unit-testable offline); `_builder.py` wires in the real `speasy.core.http.get` for those two. The read-only `bodies_and_frames` listing instead follows `literature.py`'s convention (module-level `CacheCall`-wrapped function that imports `speasy.core.http` directly, not injected) since it needs disk-persistent caching, not per-call dependency injection. Suggested branch: `feat/agent-ephemeris-tools`.

**Tech Stack:** Python, `speasy.core.http` (existing HTTP client, no new dependency), `speasy.products.variable.SpeasyVariable` / `speasy.core.data_containers.{DataContainer,VariableTimeAxis}`, `speasy.core.cache.CacheCall`, pytest + pytest-qt.

## Global Constraints

- Backend is `https://3dview.irap.omp.eu/webresources/{get_bodies,get_frames,get_trajectory,get_transform_matrices}` — no auth, `format=json` always passed explicitly.
- Non-2xx responses are plain text (not JSON) — return `response.text` verbatim as the tool's error content; no retry, no per-status special-casing.
- `sciqlop_ephemeris` and `sciqlop_transform` are **gated** (they bind into the kernel, mutating shared state); `sciqlop_orbit_bodies_and_frames` is **read-only**. All three are `thread=True` (blocking network I/O, no Qt affinity).
- Never return raw position/velocity/matrix arrays as JSON — always bind into the kernel under a caller-chosen `name` and return a compact text summary (same non-negotiable rule as `sciqlop_fetch`).
- `sciqlop_transform` returns matrices only — it does **not** apply the rotation to any existing kernel variable.
- Every `agents.tools.*` test needs pytest-qt's `qtbot` fixture and must import from `agents.tools.*` **inside** the test function (importing the package eagerly needs a `QApplication` — see `agent-tool-surface` memory).
- Reuse `fetch.py`'s existing `_var_line` helper for the per-variable summary line instead of duplicating that rendering logic.
- `bodies_and_frames` is `CacheCall(..., is_pure=True)`-wrapped with **no arguments** — its disk cache key is constant (module+qualname only). Never test it by monkeypatching `http.get` and calling the cached wrapper itself; a prior run's cached value would make the test flaky/order-dependent. Test the un-cached `_bodies_and_frames_impl` directly instead, and monkeypatch the exported `bodies_and_frames` name (not the cache internals) when testing the tool that consumes it.

---

### Task 1: `orbits.py` — time/param helpers + bodies/frames renderer

**Files:**
- Create: `SciQLop/components/agents/tools/orbits.py`
- Test: `tests/test_agent_orbits_tool.py`

**Interfaces:**
- Produces: `BASE_URL: str`; `_to_epoch(x) -> float`; `_epoch_to_3dview(t: float) -> str`; `_iso_to_ns(t: str) -> np.datetime64`; `_check_overwrite(name: str, shell_ns: dict, overwrite: bool) -> Optional[dict]`; `_time_range_params(start, stop, sampling) -> Dict[str, str]`; `render_bodies_and_frames(bodies_payload: dict, frames_payload: dict) -> str`; `_bodies_and_frames_impl() -> str` (real network, module-level `http` import, not injected); `bodies_and_frames` (the `CacheCall`-wrapped version of `_bodies_and_frames_impl`, importable and monkeypatchable as `orbits.bodies_and_frames` — this is what Task 4 wires into the tool).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_orbits_tool.py`:

```python
"""Pure logic of the ephemeris/transform tools (time helpers + rendering).

Importing anything under `SciQLop.components.agents.tools` needs a
QApplication (agents package __init__ -> chat_dock -> _builder ->
ProductsModel), so every test takes pytest-qt's `qtbot` and imports inside
the function, matching tests/test_agent_fetch_tool.py.
"""


def test_to_epoch_accepts_iso_and_number(qtbot):
    from SciQLop.components.agents.tools.orbits import _to_epoch
    assert _to_epoch(100) == 100.0
    assert _to_epoch("1970-01-01T00:01:40+00:00") == 100.0


def test_epoch_to_3dview_formats_milliseconds(qtbot):
    from SciQLop.components.agents.tools.orbits import _epoch_to_3dview
    assert _epoch_to_3dview(1577836800.0) == "2020-01-01T00:00:00.000"


def test_iso_to_ns_strips_trailing_z(qtbot):
    import numpy as np
    from SciQLop.components.agents.tools.orbits import _iso_to_ns
    assert _iso_to_ns("2026-01-01T00:00:00.000Z") == np.datetime64("2026-01-01T00:00:00.000", "ns")


def test_check_overwrite_blocks_existing_name(qtbot):
    from SciQLop.components.agents.tools.orbits import _check_overwrite
    out = _check_overwrite("X", {"X": 123}, overwrite=False)
    assert out is not None
    assert "already bound" in out["content"][0]["text"]


def test_check_overwrite_allows_when_flag_set_or_name_free(qtbot):
    from SciQLop.components.agents.tools.orbits import _check_overwrite
    assert _check_overwrite("X", {"X": 123}, overwrite=True) is None
    assert _check_overwrite("Y", {"X": 123}, overwrite=False) is None


def test_time_range_params_includes_sampling_only_when_given(qtbot):
    from SciQLop.components.agents.tools.orbits import _time_range_params
    p = _time_range_params(1577836800.0, 1577840400.0, None)
    assert p["format"] == "json"
    assert p["start"] == "2020-01-01T00:00:00.000"
    assert p["stop"] == "2020-01-01T01:00:00.000"
    assert "sampling" not in p
    p2 = _time_range_params(1577836800.0, 1577840400.0, 600)
    assert p2["sampling"] == "600"


_BODIES_PAYLOAD = {"bodies": [
    {"id": -144, "name": "Solar Orbiter", "coverage": ["2020-02-10T04:55:49.670Z", "2030-11-20T04:42:43.611Z"], "type": "SPACECRAFT"},
    {"id": 399, "name": "Earth", "coverage": ["1900-01-01T00:00:00.000Z", "2200-01-01T00:00:00.000Z"], "type": "PLANET"},
]}
_FRAMES_PAYLOAD = {"frames": [
    {"id": 1, "name": "J2000", "desc": "Earth mean equator, dynamical equinox of J2000", "center": "Sun"},
    {"id": 1601010, "name": "HEEQ", "desc": "Heliocentric Earth Equatorial", "center": "Sun"},
]}


def test_render_bodies_and_frames_lists_both_sorted_and_described(qtbot):
    from SciQLop.components.agents.tools.orbits import render_bodies_and_frames
    text = render_bodies_and_frames(_BODIES_PAYLOAD, _FRAMES_PAYLOAD)
    assert "### bodies (2)" in text
    assert "Earth, Solar Orbiter" in text  # sorted alphabetically
    assert "### frames (2)" in text
    assert "`HEEQ` — Heliocentric Earth Equatorial" in text


def test_bodies_and_frames_impl_calls_both_endpoints_and_renders(qtbot, monkeypatch):
    """Tests `_bodies_and_frames_impl` directly (NOT the cached `bodies_and_frames`
    wrapper) by monkeypatching orbits.http.get — this sidesteps speasy's
    disk-persistent CacheCall cache entirely, so the test is not flaky across
    runs (the cached wrapper has no args to key on, so any test that exercised
    it through the real cache would read stale results from a prior run)."""
    import SciQLop.components.agents.tools.orbits as orbits

    calls = []

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if url.endswith("/get_bodies"):
            return _Resp(_BODIES_PAYLOAD)
        return _Resp(_FRAMES_PAYLOAD)

    monkeypatch.setattr(orbits.http, "get", fake_get)
    text = orbits._bodies_and_frames_impl()
    assert "Earth, Solar Orbiter" in text
    assert len(calls) == 2
    assert calls[0].endswith("/get_bodies") and calls[1].endswith("/get_frames")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_orbits_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'SciQLop.components.agents.tools.orbits'`

- [ ] **Step 3: Write the implementation**

Create `SciQLop/components/agents/tools/orbits.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_orbits_tool.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/orbits.py tests/test_agent_orbits_tool.py
git commit -m "feat(agents): orbits.py time/param helpers + bodies-and-frames renderer"
```

---

### Task 2: `orbits.py` — ephemeris parsing + kernel-binding orchestration

**Files:**
- Modify: `SciQLop/components/agents/tools/orbits.py`
- Test: `tests/test_agent_orbits_tool.py`

**Interfaces:**
- Consumes (from Task 1): `BASE_URL`, `_check_overwrite`, `_time_range_params`; (from `fetch.py`, existing): `_var_line(short: str, var) -> str`.
- Produces: `parse_trajectory(payload: dict) -> Dict[str, SpeasyVariable]` (keys `"position"`, `"speed"`); `fetch_ephemeris(body: str, frame: Optional[str], start, stop, sampling, name: str, shell_ns: dict, *, overwrite: bool = False, http_get: Callable) -> dict` (MCP content shape).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_orbits_tool.py`:

```python
_TRAJECTORY_PAYLOAD = {
    "bodyid": -144, "frameid": 1601010, "frame": "HEEQ",
    "kernel": {"name": "so/mk/solo_ANC_soc-pred-mk.tm", "date": "2026-07-02T01:21:26.845Z"},
    "start": "2026-01-01T00:00:00.000Z", "stop": "2026-01-01T02:00:00.000Z",
    "sampling (s)": 3600, "units": "km/s",
    "values": [
        {"time": "2026-01-01T00:00:00.000Z", "position": [1.25759608E8, 1.968625E7, 7086599.0],
         "speed": [-6.342198848724365, -4.787736892700195, -7.029590129852295]},
        {"time": "2026-01-01T01:00:00.000Z", "position": [1.25736744E8, 1.9669028E7, 7061289.5],
         "speed": [-6.359248161315918, -4.780154228210449, -7.031221866607666]},
    ],
}


def test_parse_trajectory_builds_position_and_speed_variables(qtbot):
    from SciQLop.components.agents.tools.orbits import parse_trajectory
    mapping = parse_trajectory(_TRAJECTORY_PAYLOAD)
    assert set(mapping.keys()) == {"position", "speed"}
    pos, speed = mapping["position"], mapping["speed"]
    assert pos.shape == (2, 3) and speed.shape == (2, 3)
    assert pos.unit == "km" and speed.unit == "km/s"
    assert pos.columns == ["X", "Y", "Z"] and speed.columns == ["Vx", "Vy", "Vz"]
    assert pos.meta.get("COORDINATE_SYSTEM") == "HEEQ"
    assert pos.values[0].tolist() == [1.25759608E8, 1.968625E7, 7086599.0]


class _FakeResponse:
    def __init__(self, ok, payload=None, text=""):
        self.ok = ok
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_fetch_ephemeris_binds_dict_and_summarizes(qtbot):
    from SciQLop.components.agents.tools.orbits import fetch_ephemeris
    ns = {}
    captured = {}

    def http_get(url, params):
        captured["url"], captured["params"] = url, params
        return _FakeResponse(True, _TRAJECTORY_PAYLOAD)

    out = fetch_ephemeris("Solar Orbiter", "HEEQ", 1767225600.0, 1767232800.0, 3600,
                          "orbit", ns, http_get=http_get)
    assert "position" in ns["orbit"] and "speed" in ns["orbit"]
    text = out["content"][0]["text"]
    assert "orbit" in text and "HEEQ" in text and "2 sample" in text
    assert "to_dataframe()" in text
    assert captured["url"].endswith("/get_trajectory")
    assert captured["params"]["body"] == "Solar Orbiter"
    assert captured["params"]["frame"] == "HEEQ"


def test_fetch_ephemeris_error_response_returns_text_verbatim(qtbot):
    from SciQLop.components.agents.tools.orbits import fetch_ephemeris
    ns = {}
    out = fetch_ephemeris("NOPE", None, 0.0, 1.0, None, "orbit", ns,
                          http_get=lambda url, params: _FakeResponse(False, text="Body NOPE not found"))
    assert "orbit" not in ns
    assert out["content"][0]["text"] == "Body NOPE not found"


def test_fetch_ephemeris_respects_overwrite_guard(qtbot):
    from SciQLop.components.agents.tools.orbits import fetch_ephemeris
    ns = {"orbit": 123}
    out = fetch_ephemeris("Solar Orbiter", None, 0.0, 1.0, None, "orbit", ns,
                          http_get=lambda url, params: _FakeResponse(True, _TRAJECTORY_PAYLOAD))
    assert ns["orbit"] == 123
    assert "already bound" in out["content"][0]["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_orbits_tool.py -v -k "trajectory or ephemeris"`
Expected: FAIL — `ImportError: cannot import name 'parse_trajectory'`

- [ ] **Step 3: Write the implementation**

Add to `SciQLop/components/agents/tools/orbits.py` (extend the imports at the top and append these functions):

```python
from speasy.core.data_containers import DataContainer, VariableTimeAxis
from speasy.products.variable import SpeasyVariable

from .fetch import _var_line
```

```python
def parse_trajectory(payload: Dict[str, Any]) -> Dict[str, SpeasyVariable]:
    frame = payload.get("frame", "")
    samples = payload["values"]
    times = np.array([_iso_to_ns(s["time"]) for s in samples])
    position = np.array([s["position"] for s in samples], dtype=float)
    speed = np.array([s["speed"] for s in samples], dtype=float)
    return {
        "position": SpeasyVariable(
            axes=[VariableTimeAxis(values=times)],
            values=DataContainer(position, meta={"UNITS": "km", "COORDINATE_SYSTEM": frame}, name="position"),
            columns=["X", "Y", "Z"],
        ),
        "speed": SpeasyVariable(
            axes=[VariableTimeAxis(values=times.copy())],
            values=DataContainer(speed, meta={"UNITS": "km/s", "COORDINATE_SYSTEM": frame}, name="speed"),
            columns=["Vx", "Vy", "Vz"],
        ),
    }


def fetch_ephemeris(body: str, frame: Optional[str], start, stop, sampling, name: str,
                    shell_ns: Dict[str, Any], *, overwrite: bool = False,
                    http_get: Callable) -> Dict[str, Any]:
    blocked = _check_overwrite(name, shell_ns, overwrite)
    if blocked:
        return blocked
    params = _time_range_params(start, stop, sampling)
    params["body"] = body
    if frame:
        params["frame"] = frame
    resp = http_get(f"{BASE_URL}/get_trajectory", params=params)
    if not resp.ok:
        return {"content": [{"type": "text", "text": resp.text}]}
    mapping = parse_trajectory(resp.json())
    shell_ns[name] = mapping
    n = mapping["position"].shape[0]
    resolved_frame = mapping["position"].meta.get("COORDINATE_SYSTEM", "")
    lines = [f"fetched ephemeris for `{body}` into `{name}` — {n} sample(s), frame {resolved_frame}"]
    for short, var in mapping.items():
        lines.append(_var_line(short, var))
    lines.append(f"\nbridges: `{name}['position'].to_dataframe()`, `{name}['speed'].values`, `.time`")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_orbits_tool.py -v`
Expected: PASS (12 tests total)

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/orbits.py tests/test_agent_orbits_tool.py
git commit -m "feat(agents): orbits.py ephemeris fetch+bind (position/speed)"
```

---

### Task 3: `orbits.py` — transform-matrix parsing + kernel-binding orchestration

**Files:**
- Modify: `SciQLop/components/agents/tools/orbits.py`
- Test: `tests/test_agent_orbits_tool.py`

**Interfaces:**
- Consumes (from Task 1): `BASE_URL`, `_check_overwrite`, `_time_range_params`, `_iso_to_ns`; (from Task 2's new imports): `DataContainer`, `VariableTimeAxis`, `SpeasyVariable`, `_var_line`.
- Produces: `parse_transform(payload: dict) -> SpeasyVariable` (shape `(N, 3, 3)`); `fetch_transform(from_frame: Optional[str], to_frame: Optional[str], start, stop, sampling, name: str, shell_ns: dict, *, overwrite: bool = False, http_get: Callable) -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_orbits_tool.py`:

```python
_TRANSFORM_PAYLOAD = {
    "fromframeId": 1600399, "fromframe": "GSE", "toframeid": 1601010, "toframe": "HEEQ",
    "start": "2026-01-01T00:00:00.000Z", "stop": "2026-01-01T02:00:00.000Z", "sampling(s)": 3600,
    "values": [
        {"time": "2026-01-01T00:00:00.000Z",
         "matrix": [[-0.998632, 0.006017, 0.051945], [-0.0, -0.993359, 0.115056], [0.052292, 0.114898, 0.992]]},
        {"time": "2026-01-01T01:00:00.000Z",
         "matrix": [[-0.998627, 0.006025, 0.052029], [-0.0, -0.993363, 0.115017], [0.052377, 0.11486, 0.992]]},
    ],
}


def test_parse_transform_builds_matrix_variable(qtbot):
    from SciQLop.components.agents.tools.orbits import parse_transform
    var = parse_transform(_TRANSFORM_PAYLOAD)
    assert var.shape == (2, 3, 3)
    assert var.meta.get("from_frame") == "GSE" and var.meta.get("to_frame") == "HEEQ"
    assert var.values[0].tolist() == _TRANSFORM_PAYLOAD["values"][0]["matrix"]


def test_fetch_transform_binds_variable_and_summarizes(qtbot):
    from SciQLop.components.agents.tools.orbits import fetch_transform
    ns = {}
    captured = {}

    def http_get(url, params):
        captured["url"], captured["params"] = url, params
        return _FakeResponse(True, _TRANSFORM_PAYLOAD)

    out = fetch_transform("GSE", "HEEQ", 1767225600.0, 1767232800.0, 3600, "R", ns, http_get=http_get)
    assert ns["R"].shape == (2, 3, 3)
    text = out["content"][0]["text"]
    assert "GSE" in text and "HEEQ" in text and "R" in text and "2 sample" in text
    assert "(n,3,3)" in text
    assert captured["url"].endswith("/get_transform_matrices")
    assert captured["params"]["fromframe"] == "GSE" and captured["params"]["toframe"] == "HEEQ"


def test_fetch_transform_error_response_returns_text_verbatim(qtbot):
    from SciQLop.components.agents.tools.orbits import fetch_transform
    ns = {}
    out = fetch_transform("GSE", "NOPE", 0.0, 1.0, None, "R", ns,
                          http_get=lambda url, params: _FakeResponse(False, text="Frame id not recognized: NOPE"))
    assert "R" not in ns
    assert out["content"][0]["text"] == "Frame id not recognized: NOPE"


def test_fetch_transform_respects_overwrite_guard(qtbot):
    from SciQLop.components.agents.tools.orbits import fetch_transform
    ns = {"R": 123}
    out = fetch_transform(None, None, 0.0, 1.0, None, "R", ns,
                          http_get=lambda url, params: _FakeResponse(True, _TRANSFORM_PAYLOAD))
    assert ns["R"] == 123
    assert "already bound" in out["content"][0]["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_orbits_tool.py -v -k transform`
Expected: FAIL — `ImportError: cannot import name 'parse_transform'`

- [ ] **Step 3: Write the implementation**

Append to `SciQLop/components/agents/tools/orbits.py`:

```python
def parse_transform(payload: Dict[str, Any]) -> SpeasyVariable:
    samples = payload["values"]
    times = np.array([_iso_to_ns(s["time"]) for s in samples])
    matrices = np.array([s["matrix"] for s in samples], dtype=float)
    meta = {"from_frame": payload.get("fromframe", ""), "to_frame": payload.get("toframe", "")}
    return SpeasyVariable(
        axes=[VariableTimeAxis(values=times)],
        values=DataContainer(matrices, meta=meta, name="matrix"),
    )


def fetch_transform(from_frame: Optional[str], to_frame: Optional[str], start, stop, sampling,
                    name: str, shell_ns: Dict[str, Any], *, overwrite: bool = False,
                    http_get: Callable) -> Dict[str, Any]:
    blocked = _check_overwrite(name, shell_ns, overwrite)
    if blocked:
        return blocked
    params = _time_range_params(start, stop, sampling)
    if from_frame:
        params["fromframe"] = from_frame
    if to_frame:
        params["toframe"] = to_frame
    resp = http_get(f"{BASE_URL}/get_transform_matrices", params=params)
    if not resp.ok:
        return {"content": [{"type": "text", "text": resp.text}]}
    var = parse_transform(resp.json())
    shell_ns[name] = var
    n = var.shape[0]
    resolved_from = var.meta.get("from_frame", "") or from_frame or ""
    resolved_to = var.meta.get("to_frame", "") or to_frame or ""
    text = (f"fetched transform `{resolved_from}`→`{resolved_to}` into `{name}` "
           f"— {n} sample(s)\n{_var_line('matrix', var)}"
           f"\n\nbridges: `{name}.values` (shape (n,3,3)), `{name}.time`")
    return {"content": [{"type": "text", "text": text}]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_orbits_tool.py -v`
Expected: PASS (16 tests total)

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/orbits.py tests/test_agent_orbits_tool.py
git commit -m "feat(agents): orbits.py coordinate-transform fetch+bind (matrices)"
```

---

### Task 4: Register the three tools in `_builder.py`

**Files:**
- Modify: `SciQLop/components/agents/tools/_builder.py`
- Test: `tests/test_orbits_tool_registration.py`

**Interfaces:**
- Consumes: `orbits.bodies_and_frames`, `orbits.fetch_ephemeris`, `orbits.fetch_transform` (Tasks 1–3); existing `_builder.py` helpers `_text_tool`, `_error_content`, `_kernel_manager`.
- Produces: three new entries in `build_sciqlop_tools(main_window)`'s returned list: `sciqlop_orbit_bodies_and_frames` (read-only), `sciqlop_ephemeris` (gated), `sciqlop_transform` (gated).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orbits_tool_registration.py`:

```python
"""sciqlop_ephemeris / sciqlop_transform / sciqlop_orbit_bodies_and_frames
registration + handler wiring (needs QApplication -> qtbot)."""
import asyncio
from unittest.mock import MagicMock


def _tool(qtbot, name):
    import SciQLop.components.agents.tools._builder as builder
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_bodies_and_frames_tool_registered_read_only(qtbot):
    t = _tool(qtbot, "sciqlop_orbit_bodies_and_frames")
    assert t.get("gated", False) is False
    assert t["input_schema"]["required"] == []


def test_ephemeris_tool_registered_gated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_ephemeris")
    assert t.get("gated", False) is True
    props = t["input_schema"]["properties"]
    assert set(t["input_schema"]["required"]) == {"body", "start", "stop", "name"}
    for opt in ("frame", "sampling", "overwrite"):
        assert opt in props


def test_transform_tool_registered_gated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_transform")
    assert t.get("gated", False) is True
    props = t["input_schema"]["properties"]
    assert set(t["input_schema"]["required"]) == {"start", "stop", "name"}
    for opt in ("from_frame", "to_frame", "sampling", "overwrite"):
        assert opt in props


def test_ephemeris_handler_delegates_to_fetch_ephemeris(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    import SciQLop.components.agents.tools.orbits as orbits

    captured = {}

    def fake_fetch_ephemeris(body, frame, start, stop, sampling, name, shell_ns, **kw):
        captured.update(body=body, frame=frame, name=name, kw=kw)
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(orbits, "fetch_ephemeris", fake_fetch_ephemeris)
    monkeypatch.setattr(builder, "_kernel_manager",
                        lambda: type("KM", (), {"shell": type("S", (), {"user_ns": {}})()})())

    out = asyncio.run(_tool(qtbot, "sciqlop_ephemeris")["handler"](
        {"body": "Solar Orbiter", "frame": "HEEQ", "start": 0, "stop": 10,
         "name": "orbit", "sampling": 600, "overwrite": True}))
    assert out["content"][0]["text"] == "ok"
    assert captured["body"] == "Solar Orbiter" and captured["frame"] == "HEEQ"
    assert captured["kw"]["overwrite"] is True


def test_ephemeris_handler_errors_without_kernel(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder, "_kernel_manager", lambda: None)
    out = asyncio.run(_tool(qtbot, "sciqlop_ephemeris")["handler"](
        {"body": "Solar Orbiter", "start": 0, "stop": 1, "name": "orbit"}))
    assert "kernel is not available" in out["content"][0]["text"]


def test_transform_handler_delegates_to_fetch_transform(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    import SciQLop.components.agents.tools.orbits as orbits

    captured = {}

    def fake_fetch_transform(from_frame, to_frame, start, stop, sampling, name, shell_ns, **kw):
        captured.update(from_frame=from_frame, to_frame=to_frame, name=name)
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(orbits, "fetch_transform", fake_fetch_transform)
    monkeypatch.setattr(builder, "_kernel_manager",
                        lambda: type("KM", (), {"shell": type("S", (), {"user_ns": {}})()})())

    out = asyncio.run(_tool(qtbot, "sciqlop_transform")["handler"](
        {"from_frame": "GSE", "to_frame": "HEEQ", "start": 0, "stop": 10, "name": "R"}))
    assert out["content"][0]["text"] == "ok"
    assert captured["from_frame"] == "GSE" and captured["to_frame"] == "HEEQ"


def test_transform_handler_errors_without_kernel(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder, "_kernel_manager", lambda: None)
    out = asyncio.run(_tool(qtbot, "sciqlop_transform")["handler"](
        {"start": 0, "stop": 1, "name": "R"}))
    assert "kernel is not available" in out["content"][0]["text"]


def test_bodies_and_frames_handler_delegates_to_cached_call(qtbot, monkeypatch):
    """Monkeypatches the module-level `orbits.bodies_and_frames` (the
    CacheCall-wrapped function from Task 1) directly, rather than exercising
    it through the real disk-persistent cache — same reasoning as
    test_bodies_and_frames_impl_calls_both_endpoints_and_renders in Task 1."""
    import SciQLop.components.agents.tools.orbits as orbits
    monkeypatch.setattr(orbits, "bodies_and_frames", lambda: "### bodies (1)\nEarth")
    out = asyncio.run(_tool(qtbot, "sciqlop_orbit_bodies_and_frames")["handler"]({}))
    assert "Earth" in out["content"][0]["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orbits_tool_registration.py -v`
Expected: FAIL — `StopIteration` (tool not found) for the registration tests.

- [ ] **Step 3: Write the implementation**

In `SciQLop/components/agents/tools/_builder.py`, add these three factory functions (place them near `_describe_tool`/`_fetch_tool`, e.g. right after `_show_figure_tool`):

```python
def _orbit_bodies_frames_tool() -> Dict[str, Any]:
    from . import orbits
    return _text_tool(
        "sciqlop_orbit_bodies_and_frames",
        (
            "List valid body names (spacecraft, planets, small bodies) and frame "
            "names accepted by sciqlop_ephemeris/sciqlop_transform, from the CDPP "
            "3DView service. Cached — call before guessing a body/frame name."
        ),
        {"type": "object", "properties": {}, "required": []},
        lambda _p: orbits.bodies_and_frames(),
        thread=True,
    )


def _ephemeris_tool() -> Dict[str, Any]:
    from . import orbits
    from speasy.core import http

    def _run(payload: Dict[str, Any]) -> Any:
        km = _kernel_manager()
        if km is None:
            return _error_content("embedded IPython kernel is not available")
        return orbits.fetch_ephemeris(
            str(payload["body"]), payload.get("frame"),
            payload["start"], payload["stop"], payload.get("sampling"),
            str(payload["name"]), km.shell.user_ns,
            overwrite=bool(payload.get("overwrite", False)),
            http_get=http.get,
        )

    return _text_tool(
        "sciqlop_ephemeris",
        (
            "Fetch a spacecraft/planet/small-body's position (km) and velocity "
            "(km/s) into the embedded kernel under `name`, from the CDPP 3DView "
            "service. `body`/`frame` — call sciqlop_orbit_bodies_and_frames first "
            "if unsure of valid names; `frame` defaults to J2000. `start`/`stop` "
            "are ISO-8601 strings or POSIX seconds. `sampling` is the step in "
            "seconds (default 3600). Binds `{'position': ..., 'speed': ...}` "
            "(SpeasyVariable, columns X/Y/Z and Vx/Vy/Vz) — never returns raw "
            "arrays. Errors if `name` exists unless `overwrite=true`."
        ),
        {
            "type": "object",
            "properties": {
                "body": {"type": "string"},
                "frame": {"type": "string"},
                "start": {"type": ["string", "number"]},
                "stop": {"type": ["string", "number"]},
                "sampling": {"type": "integer"},
                "name": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
            "required": ["body", "start", "stop", "name"],
        },
        _run,
        gated=True,
        thread=True,
    )


def _transform_tool() -> Dict[str, Any]:
    from . import orbits
    from speasy.core import http

    def _run(payload: Dict[str, Any]) -> Any:
        km = _kernel_manager()
        if km is None:
            return _error_content("embedded IPython kernel is not available")
        return orbits.fetch_transform(
            payload.get("from_frame"), payload.get("to_frame"),
            payload["start"], payload["stop"], payload.get("sampling"),
            str(payload["name"]), km.shell.user_ns,
            overwrite=bool(payload.get("overwrite", False)),
            http_get=http.get,
        )

    return _text_tool(
        "sciqlop_transform",
        (
            "Fetch 3x3 rotation matrices between two coordinate frames (e.g. "
            "GSE->HEEQ) into the embedded kernel under `name`, from the CDPP "
            "3DView service — exact, not an approximation. Does NOT apply the "
            "rotation itself: interpolate the matrix time axis onto your data's "
            "time axis, then `np.einsum('nij,nj->ni', R, vectors)` in "
            "sciqlop_exec_python. `from_frame`/`to_frame` default to J2000/"
            "ECLIPJ2000; call sciqlop_orbit_bodies_and_frames first if unsure "
            "of valid names. `sampling` is the step in seconds (default 3600). "
            "Errors if `name` exists unless `overwrite=true`."
        ),
        {
            "type": "object",
            "properties": {
                "from_frame": {"type": "string"},
                "to_frame": {"type": "string"},
                "start": {"type": ["string", "number"]},
                "stop": {"type": ["string", "number"]},
                "sampling": {"type": "integer"},
                "name": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
            "required": ["start", "stop", "name"],
        },
        _run,
        gated=True,
        thread=True,
    )
```

Then wire them into `build_sciqlop_tools` and `_write_tools`:

```python
        _describe_tool(),
        _show_figure_tool(),
        _job_status_tool(),
        _list_jobs_tool(),
        _orbit_bodies_frames_tool(),
    ]
    tools.extend(_write_tools(main_window))
    return tools
```

(replacing the existing `tools = [...]` closing block in `build_sciqlop_tools`), and:

```python
    return [set_time_range, _create_panel_tool(main_window), _exec_python_tool(),
            _fetch_tool(), _ephemeris_tool(), _transform_tool(), _submit_job_tool(),
            _cancel_job_tool(), _install_package_tool()] + _notebook_write_tools() + [_run_notebook_cell_tool(), _interrupt_kernel_tool()]
```

(replacing the existing `return [...]` in `_write_tools`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orbits_tool_registration.py tests/test_agent_orbits_tool.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full existing agent-tools test suite to check for regressions**

Run: `uv run pytest tests/ -k "agent or fetch_tool or orbits" -v`
Expected: PASS, no regressions in `test_agent_fetch_tool.py`, `test_fetch_tool_registration.py`, `test_agent_describe_product.py`, etc.

- [ ] **Step 6: Commit**

```bash
git add SciQLop/components/agents/tools/_builder.py tests/test_orbits_tool_registration.py
git commit -m "feat(agents): register sciqlop_ephemeris/sciqlop_transform/sciqlop_orbit_bodies_and_frames"
```

---

## Out of scope (tracked in backlog, per the spec)

Applying a transform directly to a named kernel vector; field-aligned coordinates; generic file inspector (CDF/netCDF/HDF5).
