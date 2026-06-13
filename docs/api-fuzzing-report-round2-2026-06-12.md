# User API Fuzzing Report — Round 2 — 2026-06-12

Second live crash-hunting session against a running SciQLop instance
(`SciQLop - default` workspace, freshly restarted after the round-1 fixes),
driving `SciQLop.user_api` through the embedded IPython kernel.

Two goals: (a) regression-check the round-1 fixes
(see `api-fuzzing-report-2026-06-12.md`), (b) fuzz surfaces not covered in
round 1: **catalogs, virtual products, graph-level operations, overlay,
layers, sub-panels**.

**Headline: still no segfault, no process crash** — including 20-deep
sub-panel nesting and 10 MB catalog metadata. But round 2 found a
data-integrity bug in catalogs, a destructive ownership bug in
`remove_graph`, one incomplete round-1 fix, and a cluster of validation
problems in `create_virtual_product`.

All findings reproduced live; every snippet is a verified reproducer.
Per global workflow rules: **write a failing test first for each fix**.

---

## Regression check of round-1 fixes

All verified working on the live instance:

- graphic primitives (`Text`, `Ellipse`, `add_hline`) — via both the
  `plot_data` return value and the `panel.plots[]` enumeration path
- `plot_product('does//not//exist')` → clean `ValueError` with hint text
- `panel.save('/nonexistent/dir/x.png')` → `OSError`
- `panel.time_range = TimeRange(nan, nan)` → `ValueError` (finite check)
- `plot_panel(42)` → `TypeError: panel name must be a str, got int`
- `histogram2d(x_bins=0)` → `ValueError: histogram bins must be >= 1`
- `zoom_limit_seconds = -5` → `ValueError`
- stale plot/graph wrappers raise `ValueError: The plot/graph does not exist
  anymore` — note they only start raising **after the event loop spins**
  (deferred deletion); within the same tick they still answer. Acceptable,
  but worth knowing when writing tests.

### ❗ One incomplete fix

**#6 (round 1) NOT fully fixed** — `P.TimeRange('garbage', 'dates')` still
silently → `1970-01-01 .. 1970-01-01`. The NaN path (#7) was fixed, but the
string-parse constructor path still swallows unparseable dates. This is the
C++ `SciQLopPlotRange(str, str)` overload: either validate/parse the strings
on the Python side before calling it, or fix the overload in SciQLopPlots.

---

## 🔴 Critical

### R2-1. Catalog store desync: invalid event stored by user-api path, rejected by tscat GUI driver

```python
from SciQLop.user_api.catalogs import catalogs
catalogs.save('My Catalogs//fuzz_inverted', [("2020-01-02", "2020-01-01")])
# → returns OK, caller sees success
# MEANWHILE, async on the tscat driver worker thread (traceback to console only):
#   ValueError: start date has to be before stop date
#   (tscat/base.py _Event.__init__, via tscat_gui/tscat_driver/driver.py do_action)

catalogs.get('My Catalogs//fuzz_inverted')[0]
# <Event: 2020-01-02T00:00:00+00:00 -> 2020-01-01T00:00:00+00:00>
#   ← the INVERTED event was stored
```

Three problems in one:

1. `catalogs.save` does not validate `start <= stop` (tscat itself enforces
   it, so the user-api path is *more permissive than the backing store*).
2. The user-api store accepted the event while the tscat/GUI store rejected
   it → **the two stores now disagree** about catalog contents, silently.
3. The driver-thread exception escapes `do_action` and is invisible to the
   caller. The driver kept working in testing, but action-queue consistency
   after a failed action is unverified.

**Fix:** validate event ordering in `SciQLop/user_api/catalogs` before
dispatch (mirror tscat's rule: `start <= stop`), and surface driver-action
failures to the caller — or at minimum to a visible error channel instead of
a console traceback.

### R2-2. `remove_graph` has no ownership check — destroys graphs of OTHER plots

```python
plot_a, _       = panel.plot_data(t, y)
plot_b, graph_b = panel.plot_data(t, y)
plot_a.remove_graph(graph_b)   # returns OK — wrong plot!
graph_b.data                   # ValueError: The graph does not exist anymore.
```

`plot_a` destroyed `plot_b`'s graph. One missing `if`. Should raise
`ValueError: graph does not belong to this plot`.

---

## 🟠 Silent failures / bad errors

| # | Reproducer | Observed | Expected |
|---|---|---|---|
| R2-3 | `create_virtual_product(path, cb, product_type='Scalar')` (string, not enum) | **silently returns None**, nothing created | raise `TypeError` |
| R2-4 | `create_virtual_product('', cb, Scalar, labels=['x'])` | OK — creates a VirtualScalar **with empty path** (orphan/odd node in products tree) | raise `ValueError` |
| R2-5 | `create_virtual_product` with the same path twice | second call returns OK — silent overwrite (or shadow) | raise, or document overwrite semantics |
| R2-6 | `create_virtual_product(path, cb, Scalar)` with *any* unrelated bad arg (empty path, `cb=42`, bad `knobs_model`, …) | always the same misleading `ValueError: Scalar virtual products need exactly one label` — the label check runs first and masks every other problem | validate args in sensible order; also: signature says `labels: Optional[List[str]] = None` yet Scalar *requires* exactly one — default it sanely or fix the signature |
| R2-7 | `VirtualScalar(path, cb, label=None)` and `VirtualVector(path, cb, labels=[])` | accepted | inconsistent with `create_virtual_product`'s "exactly one label" rule — pick one behavior |
| R2-8 | `catalogs.get(None)`; VP `path=None` | raw `AttributeError: 'NoneType' object has no attribute 'split'` | `TypeError` with a message |
| R2-9 | `catalogs` module docstring uses `tscat//...` paths in every example | `KeyError: "Provider not found: 'tscat'"` — real providers are `My Catalogs` and `Remote` | fix the docstring examples |
| R2-10 | `panel.add_layer(func, scope='bogus_scope')` | accepted silently | validate scope against allowed values |
| R2-11 | no public API to **unregister** a virtual product (`VPRegistry` exposes only `get`/`register`) | temp/fuzz VPs pollute the products tree until app restart; also hurts notebook cell re-runs | add `unregister`/`remove` to the VP user API |
| R2-12 | `plot.remove_graph(42)` | raw `AttributeError: 'int' object has no attribute '_impl'` | `TypeError` |
| R2-13 | `catalogs.save(..., [("2020-01-01", "2020-01-02", "not_a_dict")])` | `ValueError: dictionary update sequence element #0 has length 1; 2 is required` | clearer message: "event meta must be a dict" |

---

## 🟡 Notes / lower priority

- `h2d.gradient = 'NotAGradient'` → the round-1 **#2 Shiboken NameError**
  again (`Error evaluating SciQLopColorMapBase.set_gradient: name
  'SciQLopPlotsBindings' is not defined`) — more evidence for fixing #2 in
  the SciQLopPlots repo; it masks the real `TypeError` across the whole
  binding surface.
- Catalog names accept 5000-char strings and embedded `//` (creates a nested
  path — appears intentional); 10 MB meta dicts accepted without complaint.
- `overlay.opacity` silently clamps to [0, 1] (5.0 → 1, -1 → 0) — acceptable.
- `overlay.level` / `overlay.position` are read-only properties (setter via
  `show(..., level=, position=)` only) — fine, just asymmetric with `opacity`.
- `speasy.Event` exposes `start_time`/`stop_time`, not `start`/`stop` —
  no bug, just a docs nicety for examples.

## ✅ What held up well (don't break these)

- **Catalogs** input validation: garbage date strings (`ParserError`), wrong
  tuple size, non-iterable events, NaN floats, out-of-range years
  (`1e15` → "year 31690708 is out of range"), negative epochs, read-only
  `Remote` provider (`PermissionError: Provider 'Remote' cannot create
  catalogs`), `create` on an existing catalog (`ValueError`), removing
  foreign events (`ValueError: Cannot identify event to remove (no UUID)`),
  path validation (`empty segment`, `must have at least provider and
  catalog name`).
- **Graph lifetime** guards post-fix: double `remove_graph`, `.data`/
  `.visible` after removal — all raise cleanly.
- `add_layer(42)` → clean `TypeError: 42 is not a callable object`.
- VP callback validation when reachable: `cb=42` → `TypeError: 42 is not a
  callable object`; scalar with 3 labels → clean ValueError; missing type
  hints on callbacks → helpful UserWarning with a fix suggestion.
- `Histogram2D.set_data` length-mismatch and string-array rejection.
- No crash from: 20-deep sub-panel nesting, cross-plot graph removal,
  out-of-range overlay opacity, huge catalog names/metas.

---

## Suggested attack order

1. **R2-1** — catalog `start <= stop` validation + driver-error surfacing
   (data integrity; the only finding that silently corrupts user data).
2. **R2-2** — `remove_graph` ownership check (one `if`, destroys user data).
3. **#6 leftover** — `TimeRange(str, str)` parse validation.
4. **R2-3..R2-7** — `create_virtual_product` validation sweep (one function,
   one test file: enum check, path check, ordering, label consistency).
5. **R2-9** — catalogs docstring provider names (trivial).
6. **R2-11** — VP unregister API (small feature, big notebook QoL).
7. **R2-8, R2-12, R2-13** — error-message polish.
8. **R2-10** — layer scope validation.

## Session leftovers on the live instance

- Fuzz virtual products under `fuzz//` plus a few `<lambda>N` provider
  entries remain in the products tree (no unregister API — restart to clear).
- All fuzz catalogs under `My Catalogs` were removed during the session.
- Round-1 leftover: none (instance was restarted before round 2).
