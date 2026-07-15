# Onboarding: generalized tutorial engine (multi-tour + plugin-registered tours)

**Date:** 2026-07-15
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — generalizes the existing `SciQLop/components/onboarding/`
component; no changes to any out-of-tree plugin repo in this round).
**Supersedes/extends:** `docs/superpowers/specs/2026-07-14-onboarding-guided-tour-design.md`
(the single "Getting Started" tour shipped from that spec becomes this
engine's first built-in tour, content unchanged).

## Problem

The onboarding tour shipped 2026-07-14 is a single hardcoded sequence:
`TOUR_STEPS` is one flat list, `TourController` has `if step_id == ...` /
`elif completion_signal_id == ...` branches wired to that one sequence's
specific steps, and completion is tracked with a single
`OnboardingSettings.tour_completed: bool`. Two new requirements don't fit
this shape:

1. **More built-in tours** — a Catalogs tour and a Settings tour, each
   independently replayable and independently "completed", not folded into
   one ever-longer sequence.
2. **Plugin-registered tours** — an out-of-tree plugin (MSA, radio, sismo,
   cdf_workbench, ...) should be able to add its own tour covering its own
   UI, without SciQLop core knowing that plugin exists ahead of time.

Requirement 2 is the one that actually forces an architecture change: a
plugin can't add an `elif` branch to `tour_controller.py`, and can't add an
entry to a core-owned `TOUR_STEPS` list. The controller has to become
generic enough that "which tour is running" carries no special cases at
all — built-in and plugin tours run through exactly the same code path.

## Decisions carried in from discussion

- **One entry point, a picker dialog.** A single "Take a Tour…" action
  (Tools menu + Welcome quickstart card) opens a dialog listing every
  registered tour (title + description); picking one runs it. No
  per-tour menu entries.
- **First-launch auto-start stays narrow.** Only the "Getting Started"
  tour auto-fires on first launch (unchanged behavior). Catalogs,
  Settings, and any plugin tour are picker-only, never auto-started.
- **Build scope for this round:** the generic engine, the picker, real
  content for Getting Started (ported, unchanged) + Catalogs + Settings,
  and a real, working plugin-registration API — verified with a test
  double, not a real out-of-tree plugin. Writing an actual tour into
  msa/radio/sismo/etc. is separate follow-up work in those repos.
- **`TourStep`/`Tour` stay plain (frozen) dataclasses, not Pydantic.**
  The project's actual boundary (confirmed by `PluginDesc`, which parses
  `plugin.json`, vs. plain-dataclass `TourStep` today) is Pydantic for
  data parsed from external/untrusted sources, dataclasses for structures
  built directly by trusted code. Tours are always constructed in Python
  — by a built-in tour module or a plugin's `load(main_window)` — never
  parsed from a file. `frozen=True` gives the same immutability with less
  ceremony than `model_config = ConfigDict(frozen=True)`.
- **`OnboardingSettings.tour_completed: bool` becomes
  `completed_tours: dict[str, bool]`, not migrated.** Existing users who
  already finished the tour will see "Getting Started" auto-fire one more
  time after this ships (the old flag is silently dropped by Pydantic's
  default extra-field handling, not read into the new schema). Accepted
  as a one-time, skippable inconvenience rather than adding migration
  code for a single local YAML field.

## Design

### File layout

```
SciQLop/components/onboarding/
  backend/
    tour.py                 # TourStep + Tour dataclasses only
    registry.py              # register_tour / get_tour / all_tours
    tour_getting_started.py  # built-in tour: today's 5 steps, ported
    tour_catalogs.py         # built-in tour: new, 4 steps
    tour_settings.py         # built-in tour: new, 2 steps
    targets.py                # resolvers (existing + new), each gains `context`
    completions.py           # completion-signal functions (extracted from controller)
    settings.py               # OnboardingSettings (completed_tours dict)
  ui/
    coach_mark.py             # unchanged
    tour_controller.py        # generalized: takes a Tour, zero step-id branching
    tour_picker.py            # new: "choose a tour" dialog
  __init__.py                 # public plugin-facing exports: Tour, TourStep, register_tour
```

### Data model

```python
@dataclass(frozen=True)
class TourStep:
    step_id: str
    title: str
    body: str
    resolver: Callable[[QWidget, dict], object | None]
    # returns a QWidget, a (QWidget, QRect) tuple, or None
    completion: Callable[[QWidget, dict], object | None] | None = None
    # returns a Signal, a (Signal, predicate) tuple, or None
    poll: bool = False
    timeout_s: float | None = None
    timeout_message: str | None = None

@dataclass(frozen=True)
class Tour:
    id: str
    title: str
    description: str
    steps: list[TourStep]
```

A `completion` callable's return value:
- `None` → dismiss-only step (today's "Got it" tip steps).
- a `Signal` → advance as soon as it fires.
- `(Signal, predicate)` → advance only when `predicate(*emitted_args)` is
  `True` (replaces the old hardcoded `if visible: advance` special-case
  for the Products/Settings dock's `visibilityChanged`).

### Registry (`backend/registry.py`)

```python
_registry: dict[str, Tour] = {}

def register_tour(tour: Tour) -> None:
    if tour.id in _registry:
        raise ValueError(f"Tour {tour.id!r} is already registered")
    if not tour.steps:
        raise ValueError(f"Tour {tour.id!r} has no steps")
    _registry[tour.id] = tour

def get_tour(tour_id: str) -> Tour | None:
    return _registry.get(tour_id)

def all_tours() -> list[Tour]:
    return list(_registry.values())
```

Built-in tours (`tour_getting_started.py`, `tour_catalogs.py`,
`tour_settings.py`) each build their `Tour` and call `register_tour` at
import time; a `register_builtin_tours()` helper imports all three,
called once during `SciQLopMainWindow` setup (before plugins load, so
plugin tours registering under the same picker are simply additive).

### Controller (`ui/tour_controller.py`)

`TourController(main_window, tour: Tour)` — no longer imports a module-level
step list. `run_tour(main_window, tour_id: str)` looks the tour up via
`get_tour`; if not found, logs a warning via the existing `_log_safely` and
no-ops rather than raising.

Generalizations (all three remove a hardcoded branch from the current code):

- `_resolve_target` calls `step.resolver(main_window, self._context)` —
  no more `if step.step_id == "overlay_vs_new_subplot"` special-case;
  `tour_catalogs.py`'s "overlay onto a plot" step resolver reads
  whatever it needs from `context` itself.
- `_show_step` unpacks a `(widget, rect)` result by `isinstance(target, tuple)`,
  not by comparing `step_id` to `"plot_product"`.
- Completion wiring replaces the three `elif completion_signal_id ==` branches
  with one generic path: call `step.completion(main_window, context)`;
  normalize a bare `Signal` to `(signal, lambda *a: True)`; connect a single
  generic slot that, on fire, stores the emitted args into
  `context[step.step_id]` and advances iff the predicate passes.

`self._context: dict[str, Any]` replaces today's one-off
`self._panel_from_step_1` attribute — it accumulates every completed step's
result automatically, keyed by `step_id`, so later steps (in any tour, core
or plugin) can read earlier ones without the controller mediating that
relationship. **Storage rule** (must be unambiguous, since
`tour_catalogs.py`'s design below assumes a later resolver can use a stored
value directly as a widget, not as a tuple): a one-arg signal emission
stores that arg bare (`context["create_panel"] = panel`, matching today's
`self._panel_from_step_1 = panel`); a zero-arg emission stores `True`; a
multi-arg emission stores the full args tuple. A dismiss-only step
(`completion is None`) stores nothing.

### Picker (`ui/tour_picker.py`)

A `QDialog` with a `QListWidget` populated from `all_tours()` at open time
(title + description per row, a "✓ Completed" suffix when
`OnboardingSettings().completed_tours.get(tour.id)` is true), and a "Start"
button (also double-click) that closes the dialog and calls
`run_tour(main_window, tour.id)`. Since it reads the registry at open time,
a plugin's tour appears automatically once registered — no core change
needed to add one.

### Entry points

- Tools menu: `"Replay Onboarding Tour"` → `"Take a Tour…"`, opens the picker.
- Welcome quickstart card: same rename, same picker.
- First-launch auto-start (`_maybe_run_onboarding_tour`): unchanged
  trigger (`workspace_loaded`, 500ms deferred), but now checks
  `not completed_tours.get("getting_started", False)` and calls
  `run_tour(main_window, "getting_started")` directly — never opens the
  picker.

### Settings

```python
class OnboardingSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Onboarding"
    completed_tours: dict[str, bool] = {}
```

`TourController._finish()` sets `completed_tours[tour.id] = True`.

### Plugin API

The entire public surface, exported from `onboarding/__init__.py`:

```python
from SciQLop.components.onboarding import Tour, TourStep, register_tour
```

A plugin calls `register_tour(Tour(...))` from its existing
`load(main_window)`. No subclassing, no namespacing convention to follow —
`register_tour` itself rejects a duplicate id.

### New tour content

**Catalogs tour** (`tour_catalogs.py`, 4 steps — resolvers to add in
`targets.py`):
1. *Interactive* — highlight the Catalogs side-tab (mirrors
   `resolve_products_side_tab`); completes on that dock's
   `visibilityChanged(True)`.
2. *Info* — highlight the catalog tree (`_catalog_tree`); explain
   right-click → "New Catalog" on a provider node. Dismiss-only: the
   action is a dynamic context-menu item, not a persistent widget.
3. *Info* — highlight the "Add Event" button (`_add_event_btn`); explain
   labeling a time interval. Dismiss-only.
4. *Info* — highlight a plot panel; explain dragging a catalog onto it,
   or right-click → Catalogs submenu, to overlay it. Dismiss-only.

**Settings tour** (`tour_settings.py`, 2 steps, deliberately light):
1. *Interactive* — highlight the Settings side-tab; completes on
   `visibilityChanged(True)` (same pattern as Catalogs step 1 and the
   existing Products step).
2. *Info* — highlight the category list (`SettingsCategories`); mention
   Appearance (instant visual feedback) and Plugins/Workspaces as the
   functional ones. Dismiss-only.

## Error handling

- A plugin's `register_tour` call runs inside its `load(main_window)`,
  which the existing plugin loader already wraps in try/except-log-continue
  (`components/plugins/backend/loader/loader.py`) — a bad registration
  (duplicate id, empty steps) drops just that plugin's tour and logs; the
  rest of the app is unaffected. No new error-handling code needed for this
  path.
- `run_tour(main_window, tour_id)` on an unregistered id logs a warning via
  `_log_safely` and no-ops — never raises into a menu-action or
  auto-start-timer callback.
- Mid-tour target-not-found keeps the existing generic poll → timeout →
  abort path, unchanged and already tour-agnostic (it never referenced a
  specific step's id).
- Everything in the original spec's Qt-lifetime-safety section (target
  destroyed mid-tour aborts gracefully, coach mark parented for normal Qt
  teardown) carries over unchanged — `CoachMark` itself isn't touched by
  this design.

## Testing

- `test_onboarding_registry.py` *(new)*: duplicate id raises, empty-steps
  raises, `get_tour`/`all_tours` reflect registrations.
- `test_onboarding_tour_getting_started.py`,
  `test_onboarding_tour_catalogs.py`, `test_onboarding_tour_settings.py`
  *(new, replacing `test_onboarding_tour_steps.py`)*: same
  shape-of-data assertions as today (step ids in order, which steps poll,
  which have a completion callable) per built-in tour.
- `test_onboarding_tour_controller.py`, `test_onboarding_targets.py`,
  `test_onboarding_integration.py`, `test_onboarding_wiring.py`: rewritten
  for the callable-based schema; controller tests in particular should
  cover the generic `context` accumulation (a later step's resolver reads
  an earlier step's stored completion args) since that behavior has no
  precedent in the current suite.
- `test_onboarding_coach_mark.py`: unchanged, `CoachMark` isn't touched.
- **New:** a test that registers a `Tour` through the public plugin API
  (`from SciQLop.components.onboarding import Tour, TourStep, register_tour`)
  using a throwaway fake tour/resolver, and asserts it appears in
  `all_tours()` and is runnable via `run_tour()` — this is what actually
  proves the plugin-registration path works end to end, not just that the
  registry dict accepts an entry.
- Picker dialog: lists all registered tours including a freshly-registered
  fake one; shows "✓ Completed" only for ids present in
  `completed_tours`; selecting + Start calls `run_tour` with the right id.
