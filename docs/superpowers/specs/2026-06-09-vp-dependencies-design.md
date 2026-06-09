# Virtual Product Dependencies — Design

**Date:** 2026-06-09
**Status:** Approved (first cut: §1–§3 + introspection-only graph exposure + cycle depth-guard)

## Motivation

A virtual product (VP) callback often needs another product's data as input — e.g. a
field-magnitude VP needs the IMF vector. Today the author calls `spz.get_data(...)`
(or another VP's callback) by hand inside the function body, threading `start`/`stop`
through manually. This is FastAPI-style dependency injection for VP callbacks: declare
the dependency in the signature, and SciQLop fetches it over the right time range and
injects the resulting `SpeasyVariable`.

Value targeted in this first cut:

- **Ergonomics** — no manual `get_data(start, stop)` plumbing; data arrives pre-fetched
  and time-aligned in the call arguments.
- **Dependency graph (visibility only)** — the marker makes edges introspectable at
  VP-creation time without running the callback, so the inspector / graph-context
  tooling can *show* what a VP depends on.

Performance (shared-cache prefetch dedupe) and reload-on-upstream-change are explicitly
deferred — see Out of Scope.

## Surface API

A `Depends` marker, mirroring the existing `Knob` marker convention exactly. Knobs are
`Annotated[type, Knob(...)]`; dependencies are `Annotated[SpeasyVariable, Depends(...)]`.

```python
from SciQLop.user_api.virtual_products import Depends, Scalar
from speasy.products import SpeasyVariable
from typing import Annotated
import numpy as np

IMF = Annotated[SpeasyVariable, Depends("speasy//amda//imf", pad=60.0)]

def field_mag(start, stop, b: IMF) -> Scalar["|B|"]:
    return b.time, np.linalg.norm(b.values, axis=1)
```

`Depends(target, *, pad=None)`:

- `target` — what to resolve. One of:
  - a product **path**: `str` with `//` separators, or `list[str]` (into `ProductsModel`)
  - a `VirtualProduct` handle (the object returned by `create_virtual_product`)
  - a `Callable[[float, float], data]` (an opaque leaf — injectable, but no graph node)
- `pad` — optional symmetric window widening for filter/edge effects. `float` seconds or
  `datetime.timedelta`. `None` ⇒ resolve over the VP's own `[start, stop]`. (String
  durations like `"60s"` are out of scope for the first cut.)

**Aliasing.** Only the `Annotated` form is supported. Reused dependencies are shortened
with an ordinary type alias (`IMF = Annotated[...]`), which `get_type_hints(...,
include_extras=True)` resolves transparently and which type checkers understand. The
inline `Product["path"]` subscript sugar was considered and explicitly dropped to keep
the surface minimal.

`Depends` is defined alongside the VP backend and re-exported from
`SciQLop.user_api.virtual_products`, the same place user code imports `Scalar`/`Vector`.

## Three-role signature split (load-bearing change)

A VP callback's parameters now carry **three** distinct roles, each identified by an
explicit marker — never by position-or-default guessing:

| Role            | Identified by                                              | Injected value                         |
|-----------------|-----------------------------------------------------------|----------------------------------------|
| `start` / `stop`| first two positional params **without** a `Depends` marker| float / datetime / datetime64 (unchanged) |
| dependency      | `Annotated[..., Depends(...)]`                             | resolved `SpeasyVariable`              |
| knob            | has a plain default, not reserved, not `Depends`          | knob value (unchanged)                 |

This fixes a latent sharp edge: `_positional_args_types` in `easy_provider.py` currently
treats *every* no-default param as a `start`/`stop` candidate, and is saved only by
slicing `[:2]`. The new extractor filters `Depends`-marked params out **first**, so a
dependency can never be mistaken for `start`/`stop`. Knobs already skip no-default params
(`extract_specs_from_callback` does `if param.default is empty: continue`), and
dependency params have no default, so the knob path needs no change.

## Resolution & injection

In `EasyProvider._invoke_callback`, before calling the user callback, for each
dependency spec:

1. Compute the resolution range: `rstart, rstop = start - pad, stop + pad` (`pad` in
   seconds; `0` when `None`).
2. Resolve `target` → `SpeasyVariable`:
   - **path** — look up the node in `ProductsModel`, call its owning provider's
     `get_data(node, rstart, rstop)`, normalize to `SpeasyVariable`.
   - **VirtualProduct** — call its provider's `get_data`.
   - **callable** — call `target(rstart, rstop)`, normalize result.
3. Inject as a kwarg keyed by the parameter name, merged with the existing knob kwargs,
   then `self._callback(*rng, **kwargs)`.

Resolution runs on the same worker thread the callback already runs on (off the GUI
thread), reusing the existing provider threading contract — no new threading surface.

A **cycle depth-guard** wraps resolution: a VP that (transitively) depends on itself
hits a bounded recursion depth and raises a clear error instead of hanging.

## Dependency graph (visibility only)

At VP creation (`EasyProvider.__init__`), after extracting the dependency specs
(analogous to `_knob_specs`), store them on the provider and surface them through the
existing `extended_metadata(ctx)` hook by adding a `"dependencies"` key. This lets the
inspector / graph-context tooling display what a VP depends on. No invalidation or
prefetch machinery is built in this cut.

## Error handling

- Unresolvable path / provider error → raise a clear error naming both the VP and the
  missing product (always, in both modes — a real misconfiguration, not a data gap).
- Dependency resolves to `None` → **debug mode raises** a clear error (so the author sees
  it); **normal mode discards**: the VP yields no data (callback is not invoked) and the
  reason is logged at debug level with the dependency's parameter name and target. A
  legitimately empty (zero-length) result is NOT treated as `None` — it flows through.
- Cyclic dependency → depth-guard raises rather than hangs.
- Debug mode (`debug=True`) continues to route through `validate_and_call`; dependency
  injection happens before validation so diagnostics see the real arguments.

## Components / files touched

- **New** `SciQLop/components/plotting/backend/dependencies.py` — `Depends` marker,
  `DependsSpec`, `extract_dependencies_from_callback(callback)`, and the resolver.
- **`easy_provider.py`** — exclude `Depends`-marked params from `start`/`stop` detection;
  compute `_dependency_specs` in `__init__`; resolve + inject in `_invoke_callback`; add
  `"dependencies"` to `extended_metadata`.
- **`SciQLop/user_api/virtual_products/__init__.py`** — re-export `Depends`.

## Testing

Characterization tests:

- dep-on-path resolves & injects the `SpeasyVariable`
- `pad` widens the resolution window (assert the provider is queried over the padded range)
- dep-on-`VirtualProduct`
- dep-on-callable
- knobs + dependencies coexisting on one callback (both injected correctly)
- `start`/`stop` type detection (float/datetime/datetime64) still correct when deps present
- debug-mode validation still runs with deps injected
- unresolvable path raises a clear error naming the VP and the missing product
- cyclic dependency hits the depth-guard and raises

## Out of scope (tracked in backlog)

- **Reload-on-upstream-change** — propagate cache invalidation through dependency edges
  so a VP re-evaluates when an upstream product changes.
- **Shared-cache prefetch dedupe** — two VPs depending on the same product over the same
  range fetch it once.
- **String pad durations** (`pad="60s"`).
- **Inline `Product["path"]` subscript sugar.**
