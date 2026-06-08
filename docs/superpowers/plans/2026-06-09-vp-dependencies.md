# Virtual Product Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a virtual-product callback declare its upstream product dependencies in its signature via `Annotated[SpeasyVariable, Depends("path", pad=...)]`, and have SciQLop resolve each dependency over the (optionally padded) time range and inject the result.

**Architecture:** A `Depends` marker (mirroring the existing `Knob` marker) lives in a new `dependencies.py` next to `easy_provider.py`. A pure extractor reads the marker from the callback signature; a resolver turns a target (product path / `VirtualProduct` / callable) into data over a time range, guarded against dependency cycles. `EasyProvider` computes the dependency specs at construction, excludes dependency parameters from `start`/`stop` detection, resolves+injects them before each callback invocation, and exposes them through `extended_metadata` for graph visibility.

**Tech Stack:** Python 3.14, `typing.Annotated`/`get_type_hints`, `inspect`, speasy `SpeasyVariable`, pytest + pytest-qt.

**Reference spec:** `docs/superpowers/specs/2026-06-09-vp-dependencies-design.md`

**Run tests with:** `uv run pytest` (use `--no-xvfb` locally if Xvfb segfaults — see `pytest-xvfb-opengl-segfault.md`).

---

### Task 1: `Depends` marker, spec, and extractor

**Files:**
- Create: `SciQLop/components/plotting/backend/dependencies.py`
- Test: `tests/test_virtual_products/test_vp_dependencies_extract.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_virtual_products/test_vp_dependencies_extract.py`:

```python
from datetime import timedelta
from typing import Annotated

from speasy.products import SpeasyVariable

from SciQLop.components.plotting.backend.dependencies import (
    Depends, DependsSpec, depends_marker, extract_dependencies_from_callback,
)


def test_extracts_path_dependency():
    def f(start: float, stop: float,
          b: Annotated[SpeasyVariable, Depends("speasy//amda//imf", pad=60.0)]):
        return None
    specs = extract_dependencies_from_callback(f)
    assert specs == [DependsSpec(name="b", target="speasy//amda//imf", pad=60.0)]


def test_pad_timedelta_normalized_to_seconds():
    def f(start: float, stop: float,
          b: Annotated[SpeasyVariable, Depends("p", pad=timedelta(minutes=1))]):
        return None
    assert extract_dependencies_from_callback(f)[0].pad == 60.0


def test_no_pad_defaults_to_zero():
    def f(start: float, stop: float,
          b: Annotated[SpeasyVariable, Depends("p")]):
        return None
    assert extract_dependencies_from_callback(f)[0].pad == 0.0


def test_ignores_params_without_marker():
    def f(start: float, stop: float, fft: int = 256):
        return None
    assert extract_dependencies_from_callback(f) == []


def test_depends_marker_detects_annotation():
    annot = Annotated[SpeasyVariable, Depends("p")]
    assert depends_marker(annot) is not None
    assert depends_marker(SpeasyVariable) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'SciQLop.components.plotting.backend.dependencies'`

- [ ] **Step 3: Write minimal implementation**

Create `SciQLop/components/plotting/backend/dependencies.py`:

```python
import inspect
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any, Callable, Optional, Union, get_args, get_origin, get_type_hints

ProductPath = Union[str, list]
DependencyTarget = Union[ProductPath, "object", Callable[[float, float], Any]]


@dataclass(frozen=True, slots=True)
class Depends:
    """Signature marker declaring a virtual-product dependency.

    Used as ``Annotated[SpeasyVariable, Depends(target, pad=...)]``. ``target`` is a
    product path (``"a//b"`` or ``["a", "b"]``), a ``VirtualProduct`` handle, or a
    ``callable(start, stop)``. ``pad`` widens the resolution window symmetrically
    (seconds as ``float`` or ``datetime.timedelta``)."""
    target: DependencyTarget
    pad: Optional[Union[float, timedelta]] = None


@dataclass(frozen=True, slots=True)
class DependsSpec:
    name: str
    target: DependencyTarget
    pad: float  # seconds, 0.0 when unset


def _pad_seconds(pad) -> float:
    if pad is None:
        return 0.0
    if isinstance(pad, timedelta):
        return pad.total_seconds()
    return float(pad)


def depends_marker(annotation) -> Optional[Depends]:
    if get_origin(annotation) is Annotated:
        for extra in get_args(annotation)[1:]:
            if isinstance(extra, Depends):
                return extra
    return None


def extract_dependencies_from_callback(callback) -> list:
    try:
        hints = get_type_hints(callback, include_extras=True)
    except (NameError, TypeError):
        hints = {}
    sig = inspect.signature(callback)
    specs = []
    for name, param in sig.parameters.items():
        marker = depends_marker(hints.get(name, param.annotation))
        if marker is not None:
            specs.append(DependsSpec(name=name, target=marker.target,
                                     pad=_pad_seconds(marker.pad)))
    return specs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_extract.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/dependencies.py tests/test_virtual_products/test_vp_dependencies_extract.py
git commit -m "feat(vp): Depends marker + dependency extractor

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Resolver with cycle depth-guard

**Files:**
- Modify: `SciQLop/components/plotting/backend/dependencies.py`
- Test: `tests/test_virtual_products/test_vp_dependencies_resolve.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_virtual_products/test_vp_dependencies_resolve.py`:

```python
import pytest

from SciQLop.components.plotting.backend.dependencies import (
    DependsSpec, describe_target, resolve_dependency,
)


def test_resolve_callable_applies_pad():
    seen = {}
    def upstream(start, stop):
        seen["range"] = (start, stop)
        return ("UPSTREAM",)
    spec = DependsSpec(name="b", target=upstream, pad=5.0)
    result = resolve_dependency(spec, 100.0, 200.0)
    assert result == ("UPSTREAM",)
    assert seen["range"] == (95.0, 205.0)


def test_cycle_depth_guard_raises():
    holder = {}
    def recursive(start, stop):
        return resolve_dependency(holder["spec"], start, stop)
    spec = DependsSpec(name="x", target=recursive, pad=0.0)
    holder["spec"] = spec
    with pytest.raises(RecursionError) as ei:
        resolve_dependency(spec, 0.0, 1.0)
    assert "cycle" in str(ei.value).lower()


def test_describe_target_for_path_and_list():
    assert describe_target("a//b") == "a//b"
    assert describe_target(["a", "b"]) == "a//b"


def test_describe_target_for_callable():
    def myfunc(start, stop):
        return None
    assert "myfunc" in describe_target(myfunc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_resolve.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_dependency'`

- [ ] **Step 3: Write minimal implementation**

Append to `SciQLop/components/plotting/backend/dependencies.py`:

```python
import threading

_MAX_DEPTH = 16
_state = threading.local()


def describe_target(target) -> str:
    if isinstance(target, str):
        return target
    if isinstance(target, list):
        return "//".join(target)
    path = getattr(target, "path", None)
    if isinstance(path, str):
        return path
    return getattr(target, "__qualname__", None) or repr(target)


def _resolve_path(target, start: float, stop: float):
    from SciQLop.core.models import products
    from SciQLop.components.plotting.backend.data_provider import providers
    path = target.split("//") if isinstance(target, str) else list(target)
    node = products.node(path)
    if node is None:
        raise ValueError(f"product not found: {'//'.join(path)}")
    provider = providers.get(node.provider())
    if provider is None:
        raise ValueError(f"no provider for product: {'//'.join(path)}")
    return provider.get_data(node, start, stop)


def _resolve_target(target, start: float, stop: float):
    from SciQLop.user_api.virtual_products import VirtualProduct
    if isinstance(target, VirtualProduct):
        return target._impl.get_data(None, start, stop)
    if isinstance(target, (str, list)):
        return _resolve_path(target, start, stop)
    if callable(target):
        return target(start, stop)
    raise TypeError(f"unsupported dependency target: {target!r}")


def resolve_dependency(spec, start: float, stop: float):
    depth = getattr(_state, "depth", 0)
    if depth >= _MAX_DEPTH:
        raise RecursionError(
            f"dependency resolution exceeded depth {_MAX_DEPTH} resolving "
            f"{describe_target(spec.target)!r} — possible dependency cycle")
    _state.depth = depth + 1
    try:
        return _resolve_target(spec.target, start - spec.pad, stop + spec.pad)
    finally:
        _state.depth = depth
```

Note: the deferred imports inside `_resolve_path`/`_resolve_target` are intentional — `SciQLop.user_api.virtual_products` imports `easy_provider`, which imports this module, so a top-level import here would be circular.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_resolve.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/dependencies.py tests/test_virtual_products/test_vp_dependencies_resolve.py
git commit -m "feat(vp): dependency resolver with cycle depth-guard

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Integrate into `EasyProvider` (role split + inject)

**Files:**
- Modify: `SciQLop/components/plotting/backend/easy_provider.py`
- Test: `tests/test_virtual_products/test_vp_dependencies_integration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_virtual_products/test_vp_dependencies_integration.py`:

```python
from datetime import datetime
from typing import Annotated

import numpy as np
import pytest
from speasy.products import SpeasyVariable

from SciQLop.user_api.knobs import Knob
from SciQLop.components.plotting.backend.dependencies import Depends


@pytest.fixture(autouse=True)
def _isolate_products(qapp, monkeypatch):
    from SciQLop.core.models import products
    monkeypatch.setattr(products, "add_node", lambda *a, **k: None)


def _make_scalar(callback):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    return EasyScalar(path=f"vp/{id(callback):x}", get_data_callback=callback,
                      component_name="x", metadata={})


def test_callable_dependency_injected_with_pad():
    seen = {}
    def upstream(start, stop):
        seen["range"] = (start, stop)
        return ("UPSTREAM",)
    def cb(start: float, stop: float,
           b: Annotated[SpeasyVariable, Depends(upstream, pad=5.0)]):
        seen["b"] = b
        return np.array([start, stop]), np.array([0.0, 0.0])
    _make_scalar(cb).get_data(None, 100.0, 200.0)
    assert seen["b"] == ("UPSTREAM",)
    assert seen["range"] == (95.0, 205.0)


def test_path_dependency_resolves_through_provider(monkeypatch):
    from SciQLop.core.models import products
    from SciQLop.components.plotting.backend import data_provider
    captured = {}

    class FakeNode:
        def provider(self):
            return "FakeProv"

    class FakeProv:
        def get_data(self, node, start, stop):
            captured["call"] = (start, stop)
            return ("DATA",)

    monkeypatch.setattr(products, "node",
                        lambda path: FakeNode() if path == ["a", "b"] else None)
    monkeypatch.setitem(data_provider.providers, "FakeProv", FakeProv())

    def cb(start: float, stop: float,
           dep: Annotated[SpeasyVariable, Depends("a//b", pad=1.0)]):
        captured["dep"] = dep
        return np.array([start]), np.array([0.0])
    _make_scalar(cb).get_data(None, 10.0, 20.0)
    assert captured["dep"] == ("DATA",)
    assert captured["call"] == (9.0, 21.0)


def test_virtualproduct_dependency():
    from SciQLop.user_api.virtual_products import (
        create_virtual_product, VirtualProductType,
    )
    def upstream_cb(start: float, stop: float):
        return np.array([start, stop]), np.array([1.0, 2.0])
    up = create_virtual_product("up/vp", upstream_cb,
                                VirtualProductType.Scalar, labels=["u"])
    seen = {}
    def cb(start: float, stop: float,
           dep: Annotated[SpeasyVariable, Depends(up)]):
        seen["dep"] = dep
        return np.array([start]), np.array([0.0])
    _make_scalar(cb).get_data(None, 0.0, 10.0)
    assert isinstance(seen["dep"], SpeasyVariable)


def test_knob_and_dependency_coexist():
    seen = {}
    def upstream(start, stop):
        return ("U",)
    def cb(start: float, stop: float,
           dep: Annotated[SpeasyVariable, Depends(upstream)],
           gain: Annotated[int, Knob(min=1, max=10)] = 2):
        seen["dep"], seen["gain"] = dep, gain
        return np.array([start]), np.array([float(gain)])
    p = _make_scalar(cb)
    assert [s.name for s in p.get_knobs("any")] == ["gain"]
    p.get_data(None, 0.0, 1.0, knobs={"gain": 5})
    assert seen["dep"] == ("U",) and seen["gain"] == 5


def test_start_stop_type_detection_with_dependency():
    seen = {}
    def upstream(start, stop):
        return ("U",)
    def cb(start: datetime, stop: datetime,
           dep: Annotated[SpeasyVariable, Depends(upstream)]):
        seen["types"] = (type(start), type(stop))
        return np.array([0.0]), np.array([0.0])
    _make_scalar(cb).get_data(None, 0.0, 1.0)
    assert seen["types"] == (datetime, datetime)


def test_unresolvable_path_raises(monkeypatch):
    from SciQLop.core.models import products
    monkeypatch.setattr(products, "node", lambda path: None)
    def cb(start: float, stop: float,
           dep: Annotated[SpeasyVariable, Depends("missing//x")]):
        return np.array([start]), np.array([0.0])
    p = _make_scalar(cb)
    with pytest.raises(RuntimeError) as ei:
        p.get_data(None, 0.0, 1.0)
    msg = str(ei.value)
    assert "missing//x" in msg and "dep" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_integration.py -v`
Expected: FAIL — dependencies are not injected, so `cb` is called without `b`/`dep` and raises `TypeError: missing a required argument`.

- [ ] **Step 3: Write minimal implementation**

In `SciQLop/components/plotting/backend/easy_provider.py`:

(a) Add the import near the other backend imports (after the `from SciQLop.components.plotting.backend.data_provider import ...` line):

```python
from SciQLop.components.plotting.backend.dependencies import (
    depends_marker, describe_target, extract_dependencies_from_callback, resolve_dependency,
)
```

(b) Replace `_positional_args_types` so dependency params are excluded:

```python
def _positional_args_types(callback: VirtualProductCallback) -> List[type]:
    sig = signature(callback, eval_str=True)
    return [
        v.annotation for v in sig.parameters.values()
        if v.default == v.empty and depends_marker(v.annotation) is None
    ]
```

(c) In `EasyProvider.__init__`, immediately after `self._knob_specs = self._compute_knob_specs(callback, knobs_model)`, add:

```python
        self._dependency_specs = extract_dependencies_from_callback(callback)
```

(d) Add a resolver method to `EasyProvider` (place it just before `_invoke_callback`):

```python
    def _resolve_dependencies(self, start, stop) -> dict:
        out = {}
        for spec in self._dependency_specs:
            try:
                out[spec.name] = resolve_dependency(spec, start, stop)
            except Exception as e:
                raise RuntimeError(
                    f"{self.name}: failed to resolve dependency '{spec.name}' "
                    f"({describe_target(spec.target)}): {e}") from e
        return out
```

(e) In `_invoke_callback`, after the `kwargs = ...` block (both branches) and before the `with tracing.zone(...)` line, inject:

```python
        kwargs.update(self._resolve_dependencies(start, stop))
```

The surrounding code for reference (start/stop here are the original float epoch values, which is what providers expect):

```python
    def _invoke_callback(self, start, stop, knobs):
        rng = self._apply_range(start, stop)
        if self._knobs_model is not None:
            model = self._knobs_model(**(knobs or {}))
            kwargs = {self._knobs_kwarg_name: model}
        else:
            kwargs = dict(knobs or {})
        kwargs.update(self._resolve_dependencies(start, stop))
        with tracing.zone("vp.callback", cat="vp",
                          vp=self.name, n_knobs=len(kwargs),
                          start=float(start), stop=float(stop)):
            ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_integration.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the existing knob/VP suite to confirm no regression**

Run: `uv run pytest tests/test_virtual_products -v`
Expected: PASS (all existing tests still green)

- [ ] **Step 6: Commit**

```bash
git add SciQLop/components/plotting/backend/easy_provider.py tests/test_virtual_products/test_vp_dependencies_integration.py
git commit -m "feat(vp): resolve and inject signature-declared dependencies

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Expose dependencies in `extended_metadata`

**Files:**
- Modify: `SciQLop/components/plotting/backend/easy_provider.py` (the `extended_metadata` method)
- Test: `tests/test_virtual_products/test_vp_dependencies_integration.py` (add one test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_virtual_products/test_vp_dependencies_integration.py`:

```python
def test_extended_metadata_lists_dependencies():
    def cb(start: float, stop: float,
           dep: Annotated[SpeasyVariable, Depends("a//b", pad=3.0)]):
        return np.array([start]), np.array([0.0])
    md = _make_scalar(cb).extended_metadata(None)
    assert md["dependencies"] == [{"name": "dep", "target": "a//b", "pad": 3.0}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_integration.py::test_extended_metadata_lists_dependencies -v`
Expected: FAIL with `KeyError: 'dependencies'`

- [ ] **Step 3: Write minimal implementation**

In `EasyProvider.extended_metadata`, add a `"dependencies"` key to the returned dict (alongside the existing `"knob_specs"` entry):

```python
            "dependencies": [
                {"name": s.name, "target": describe_target(s.target), "pad": s.pad}
                for s in self._dependency_specs
            ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_integration.py::test_extended_metadata_lists_dependencies -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/plotting/backend/easy_provider.py tests/test_virtual_products/test_vp_dependencies_integration.py
git commit -m "feat(vp): expose dependencies in extended_metadata

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Re-export `Depends` from the public user API

**Files:**
- Modify: `SciQLop/user_api/virtual_products/__init__.py`
- Test: `tests/test_virtual_products/test_vp_dependencies_extract.py` (add one test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_virtual_products/test_vp_dependencies_extract.py`:

```python
def test_depends_is_reexported_from_user_api():
    from SciQLop.user_api.virtual_products import Depends as PublicDepends
    from SciQLop.components.plotting.backend.dependencies import Depends as BackendDepends
    assert PublicDepends is BackendDepends
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_extract.py::test_depends_is_reexported_from_user_api -v`
Expected: FAIL with `ImportError: cannot import name 'Depends'`

- [ ] **Step 3: Write minimal implementation**

In `SciQLop/user_api/virtual_products/__init__.py`, add to the top-level imports (next to the existing `from SciQLop.components.plotting.backend.easy_provider import ...` line):

```python
from SciQLop.components.plotting.backend.dependencies import Depends
```

And extend the bottom re-export line to keep the public surface together:

```python
from SciQLop.user_api.virtual_products.types import Scalar, Vector, MultiComponent, Spectrogram
```

(leave the existing `types` import as-is; the new `Depends` import above is sufficient.)

Also add a short note to the `create_virtual_product` docstring `Notes` section so the feature is discoverable:

```python
        - A callback parameter annotated ``Annotated[SpeasyVariable, Depends("a//b", pad=...)]`` declares a dependency: SciQLop resolves that product over the (optionally padded) time range and injects the result as that argument. The target may be a product path, a VirtualProduct, or a callable(start, stop).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_virtual_products/test_vp_dependencies_extract.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Full suite sanity check**

Run: `uv run pytest tests/test_virtual_products tests/test_vp_types.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add SciQLop/user_api/virtual_products/__init__.py tests/test_virtual_products/test_vp_dependencies_extract.py
git commit -m "feat(vp): re-export Depends from public virtual_products API

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §Surface API (`Depends(target, pad)`, path/VP/callable targets, float/timedelta pad, `Annotated`-only) → Task 1 (marker + extractor) + Task 2 (resolver) + Task 5 (re-export).
- §Three-role signature split → Task 3 step 3(b) (`_positional_args_types` excludes `Depends`-marked params) + `test_start_stop_type_detection_with_dependency` + `test_knob_and_dependency_coexist`.
- §Resolution & injection (padded range, path/VP/callable, same worker thread) → Task 2 + Task 3 step 3(d/e).
- §Cycle depth-guard → Task 2 (`resolve_dependency` depth counter) + `test_cycle_depth_guard_raises`.
- §Dependency graph (visibility only via `extended_metadata`) → Task 4.
- §Error handling (clear error naming VP + product) → Task 3 `_resolve_dependencies` wrap + `test_unresolvable_path_raises`.
- §Testing bullets → covered across Task 1–5 tests (path, pad, VP, callable, knobs+deps, type detection, debug path unaffected since injection precedes the `debug` branch, unresolvable error, cycle).

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step shows complete code.

**Type consistency:** `Depends`, `DependsSpec`, `depends_marker`, `describe_target`, `extract_dependencies_from_callback`, `resolve_dependency` are defined in Tasks 1–2 and referenced with identical names/signatures in Tasks 3–5. `EasyProvider._dependency_specs` set in 3(c) and read in 3(d) and Task 4. `_resolve_dependencies` defined in 3(d), called in 3(e).

**Note on debug mode:** dependency injection happens in `_invoke_callback` *before* the `if self._debug:` branch, so the `validate_and_call` path receives the injected kwargs unchanged — no separate task needed.
