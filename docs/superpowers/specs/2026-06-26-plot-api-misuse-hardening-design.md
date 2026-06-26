# Plot API Misuse Hardening — Design

**Date:** 2026-06-26
**Status:** Approved (pending implementation plan)
**Scope:** Make the public plot API harder to misuse, across two repos: the
SciQLopPlots root fix for silent callback failures, and the SciQLop `user_api`
discoverability hardening. Spec covers both; implementation deferred.

## Problem

The public plotting surface is too easy to misuse in two ways:

1. **Silent callback failure.** A *callback* plot whose function returns
   multiple components, called without `labels`, silently produces a
   single-line graph that cannot show all components — no error, just a wrong
   or empty plot.
2. **Hidden, undocumented arguments.** Load-bearing options
   (`plot_type`, `graph_type`, `name`, `labels`, `colors`, `y_log_scale`,
   `z_log_scale`) travel through an opaque `**kwargs`. They appear in no
   signature, and the docstrings only mention `plot_type`/`graph_type`.
   `plot_function` has no docstring at all.

### Root cause (verified)

`SciQLopPlots/src/SciQLopPlot.cpp`, `plot_impl()` (~L958–989), chooses the graph
class for a callable by **label count**, not data:

```cpp
case GraphType::Line:
    if (labels.size() <= 1)
        plottable = add_plottable<SciQLopSingleLineGraphFunction>(callable, labels, metaData);
    else
        plottable = add_plottable<SciQLopLineGraphFunction>(callable, labels, metaData);
```

A headless probe confirmed the behavior and the fix premise:

| Call | Graph class | Components |
|---|---|---|
| scalar callback, no labels | `SciQLopSingleLineGraphFunction` | 1 (ok) |
| scalar callback, `["y"]` | `SciQLopSingleLineGraphFunction` | 1, named (ok) |
| **multi-component callback, no labels** | `SciQLopSingleLineGraphFunction` | **1 (wrong)** |
| multi-component callback, `["a","b","c"]` | `SciQLopLineGraphFunction` | **0 at creation**, sized on first data |

The last row is the key finding: `SciQLopLineGraphFunction` reports
`line_count == 0` *before any data* and populates components on first fetch — it
**sizes from the data, not from the labels**. So routing all line callbacks to
that class fixes multi-component rendering with labels optional.

This also means the count cannot be known on the Python side before the callback
runs, so the fix must live where the data arrives (C++), not in `user_api`.

## Part A — SciQLopPlots root fix

**Goal:** function/line graphs auto-size to the data's component count;
`labels` becomes cosmetic.

### Change

In `plot_impl()` for `GraphType::Line` with a callable, stop branching on
`labels.size() <= 1` — always use `SciQLopLineGraphFunction` (data-sized).
A scalar callback then yields one line; a multi-component callback yields one
line per component, regardless of whether labels were supplied.

### Auto-naming

When labels are absent or fewer than the data's component count, derive
component names from a **base name**:

- 1 component  → `base`
- N&nbsp;>&nbsp;1 components → `base[0]`, `base[1]`, …, `base[N-1]`

`base` comes from the graph name / naming hint passed by the caller
(see Part B — `user_api` passes `f.__name__` for function plots). Naming happens
where N is known: in the C++ data-arrival path (e.g. `_configure_plotable` /
the component-creation slot), since the Python side never learns N.

### Open author decision (recorded, not blocking)

`SciQLopSingleLineGraphFunction` is presumably a single-component fast-path.
Always using `SciQLopLineGraphFunction` means single-component callbacks lose
that fast-path. Author's call whether to:

- (a) drop `SingleLine` for callables entirely (simplest), or
- (b) keep it as an explicit opt-in (e.g. a flag), defaulting to the
  data-sized class.

This spec assumes (a) unless the SciQLopPlots implementation plan chooses (b).

### Files (SciQLopPlots)

- `src/SciQLopPlot.cpp` — `plot_impl()` graph-class selection + component
  naming from base name.
- Possibly `src/SciQLopLineGraph.cpp` / component-creation path — confirm/wire
  data-driven naming when labels are short.

### Build/release

SciQLopPlots is built and released by the maintainer. This repo does not build
it. Part A ships as a normal SciQLopPlots release; SciQLop consumes it via a
version-pin bump (see Sequencing).

## Part B — SciQLop `user_api` discoverability hardening

**Goal:** the load-bearing options are visible in signatures and documented;
nothing about misuse is silent.

### Change

Promote the seven options from `**kwargs` to explicit **keyword-only**
parameters with a private `_UNSET` sentinel, forwarding each downstream only
when the caller actually set it:

```python
_UNSET = object()

def plot_function(self, f, plot_index=-1, *, labels=_UNSET, name=_UNSET,
                  graph_type=_UNSET, plot_type=_UNSET, colors=_UNSET,
                  y_log_scale=_UNSET, z_log_scale=_UNSET, **kwargs):
    if labels is not _UNSET: kwargs["labels"] = labels
    # … one line per promoted option …
```

This preserves exact present/absent semantics (we never start sending a default
to a C++ layer that previously saw nothing) and keeps `**kwargs` for niche /
graph-specific options (`gradient`, waterfall `offsets/normalize/gain`,
histogram `key_bins/value_bins`).

### Surface

Promote consistently across the methods that share the trap:

- `PlotPanel.plot`, `plot_product`, `plot_data`, `plot_function`
  (`SciQLop/user_api/plot/_panel.py`)
- Per-plot mirrors: `XYPlot.plot` / `scatter`, `TimeSeriesPlot.plot`,
  `ProjectionPlot.plot` (`SciQLop/user_api/plot/_plots.py`)

### Docstrings

- `plot_function` gains a full docstring.
- Each promoted param gets a one-line description.
- `labels` documents the count-from-data semantics: component names are
  cosmetic; the number of lines is detected from the callback's output.

### Naming hint

For function plots, pass `f.__name__` as the default naming hint (e.g. via
`name`) when the caller supplies neither `name` nor `labels`, so Part A can
auto-name components.

### Files (SciQLop)

- `SciQLop/user_api/plot/_panel.py` — promote params + docstrings on the four
  panel methods; pass `f.__name__` hint in `plot_function`.
- `SciQLop/user_api/plot/_plots.py` — promote params + docstrings on the
  per-plot `plot()` / `scatter()` mirrors.
- Tests under `tests/` covering: each promoted param reaches the impl; omitted
  params are not forwarded (sentinel discipline); existing kwargs call sites
  still work; `plot_function` naming hint applied.

## Sequencing / dependency

Part B is additive and ships independently of Part A — it improves
discoverability even before the C++ fix lands.

The docstring claim that `labels` is optional for multi-component callbacks is
only true once the SciQLopPlots pin is bumped to the release containing Part A.
Until then, multi-component callbacks still need `labels`. The docstring wording
and the `pyproject.toml` SciQLopPlots pin bump must land together so docs never
over-promise relative to the installed SciQLopPlots.

## Backward compatibility

- **Part B:** keyword-only params + `_UNSET` sentinel forwarding + retained
  `**kwargs` → no existing call site changes behavior. Promoting a kwarg that
  was passed by keyword simply binds it to the named param with identical
  forwarding.
- **Part A:** turns a silently-wrong single-line render into a correct
  multi-line one — a strict improvement. Scalar callbacks are unaffected
  (still one line, now via the data-sized class).
- Return types unchanged in both parts.

## Out of scope

- Fluent/builder redesign of the plot API.
- A typed `PlotOptions` dataclass / Pydantic options object.
- A creation-time probe / double-fetch path to discover component count
  (rejected: would block the main thread for network-backed callbacks).
- A `user_api`-side "validate & report" safety net for users on a pre-Part-A
  SciQLopPlots. Reconsider only if the pin bump must lag the docs.
