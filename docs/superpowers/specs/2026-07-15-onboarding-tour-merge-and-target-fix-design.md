# Onboarding: fix broken product target, merge the three built-in tours into one

**Date:** 2026-07-15
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — `SciQLop/components/onboarding/` only)
**Supersedes/extends:** `docs/superpowers/specs/2026-07-15-onboarding-tutorial-engine-design.md`
(the engine — `Tour`/`TourStep`, registry, controller, picker, plugin API —
is unchanged; this spec only changes which built-in tours are registered
and what one of the existing steps targets).

## Problem

Two observations from using the shipped tour:

1. **The tour appears to stop right after the user opens the Products
   browser.** Root cause, confirmed by reading the resolver against the
   live speasy inventory: `CANDIDATE_PRODUCT_PATHS` in
   `backend/targets.py` lists paths like `["cda", "MMS", "MMS1", "FGM",
   "mms1_fgm_b_gse_srvy_l2"]` — i.e. it assumes the product tree's
   top-level rows are provider names. They aren't. The real tree is
   rooted at a single `"speasy"` node; `amda`/`cda`/etc. are its
   children. `find_index_by_path` therefore never matches row 0 for any
   candidate, `resolve_first_candidate_product` always returns `None`,
   the `plot_product` step (which does `poll=True`, `timeout_s=10.0`)
   polls for 10s and times out, and `TourController.abort()` ends the
   tour silently. So the tour was never designed to stop at the product
   tree — the very next step (drill into and highlight one specific
   product row) has been dead code since it shipped.

2. **Three separate tours (Getting Started / Catalogs / Settings)
   undercut the point of a tour** — a new user should get one continuous
   overview of the app's features, not have to separately discover and
   launch three picker entries.

## Fix 1 — correct the product target

Verified live against `spz.inventories.tree` that the following path is
real, lightweight (single parameter, no heavy dataset), and has broad
time coverage:

```
speasy → amda → Parameters → ACE → MFI → "final / prelim" → b_gse
```

(`"final / prelim"` is one tree node — AMDA's inventory renames it from
the dict key `ace_imf_all` to this literal display string; it is not two
separate "final" and "prelim" nodes.)

`CANDIDATE_PRODUCT_PATHS` (`backend/targets.py`) is replaced with this
single verified entry, dropping the three broken guesses (which were
also independently wrong beyond the missing `"speasy"` prefix — e.g.
`Clusters`/`Cluster1` vs. the real `Cluster`/`Cluster_1`):

```python
CANDIDATE_PRODUCT_PATHS: list[list[str]] = [
    ["speasy", "amda", "Parameters", "ACE", "MFI", "final / prelim", "b_gse"],
]
```

`resolve_first_candidate_product` keeps its existing "first match wins"
loop structure unchanged — this keeps the door open for adding more
fallback candidates later without touching the resolver itself. No other
change to `plot_product` (its title/body text is already generic enough
to describe drag-to-plot regardless of which product it targets).

## Fix 2 — merge the three built-in tours into one

The engine (`Tour`/`TourStep`/registry/controller/picker) from the prior
spec is unchanged — this is purely a change to *which* `Tour` objects
get built and registered.

**Target shape:** a single `Tour(id="getting_started", title="Getting
Started", ...)` whose `steps` is the concatenation, in this order:

1. `create_panel` (was: Getting Started)
2. `open_products`
3. `plot_product` — now actually resolves (Fix 1)
4. `overlay_vs_new_subplot`
5. `shortcut_tip`
6. `open_catalogs` (was: Catalogs tour)
7. `create_catalog`
8. `add_event`
9. `overlay_catalog`
10. `open_settings` (was: Settings tour)
11. `browse_categories`

Rationale for the order: core plotting workflow first, catalogs
(secondary feature) next, settings (housekeeping) last. All 11
`step_id`s are already globally unique (verified — no rename needed).

Kept as `id="getting_started"` and `title="Getting Started"` (explicit
choice — not renamed to something broader) so `mainwindow.py`'s
auto-run-on-first-launch and `_start_tour("getting_started")` need zero
changes.

**Side effect worth calling out:** because a real plot now exists by the
time the merged tour reaches `overlay_catalog` (created earlier in the
same run, in steps 1–3), that step's `resolve_any_plot_with_data`
precondition is satisfied without a fresh 15s timeout risk the way it
had as a standalone tour entry point.

**File layout:**
- `tour_catalogs.py` and `tour_settings.py` stop building a `Tour` or
  calling `register_tour`. They export a plain step list instead:
  `CATALOGS_STEPS: list[TourStep]`, `SETTINGS_STEPS: list[TourStep]`.
- `tour_getting_started.py` imports both step lists and concatenates
  them into `GETTING_STARTED.steps`, then calls `register_tour` once —
  the only registration call left in the three modules.
- `registry.register_builtin_tours()` only needs to import
  `tour_getting_started` (which transitively imports the other two for
  their step lists). It no longer imports `tour_catalogs`/`tour_settings`
  directly for registration purposes.

**Picker impact:** `all_tours()` now returns exactly one `Tour`. The
"Take a Tour" dialog shows one entry instead of three. No picker code
changes — `TourPicker` already just renders whatever `all_tours()`
returns.

**Not doing:** no settings migration for
`OnboardingSettings().completed_tours` — a user who already completed
only `"catalogs"` or `"settings"` (unlikely; this feature shipped hours
before this fix) will simply see `"getting_started"` as not-yet-completed
and get the merged tour once. Consistent with the "not migrated,
accepted as one-time inconvenience" decision already made in the prior
spec for the same settings dict.

## Test changes

- `test_onboarding_tour_catalogs.py` / `test_onboarding_tour_settings.py`:
  stop asserting `registry.get_tour("catalogs")` /
  `registry.get_tour("settings")` return a registered `Tour` (there isn't
  one anymore). Keep the step-content assertions (order, poll/timeout,
  completion presence) against `CATALOGS_STEPS`/`SETTINGS_STEPS`.
- `test_onboarding_tour_getting_started.py`: step-order assertion becomes
  the full 11-`step_id` list; poll/timeout/completion assertions extend
  to cover the added steps (`add_event`, `overlay_catalog` poll with
  timeout; the rest don't).
- `test_onboarding_tour_picker.py`: `test_picker_lists_all_registered_tours`
  asserts `registered_ids == {"getting_started"}` instead of a superset
  check against three ids. `test_picker_marks_completed_tours` and
  `test_start_selected_starts_the_selected_tour` currently exercise
  picker behavior using `"settings"`/`"catalogs"` as a second/third
  entry — rewritten to use `"getting_started"` as the only entry
  (behavior under test — completed-marking, start-selected — is
  unaffected by which tour id is used).
- New/extended coverage: a resolver-level test that
  `resolve_first_candidate_product` finds the ACE/MFI/b_gse row given a
  fake model shaped like the real tree (`speasy → amda → Parameters →
  ACE → MFI → "final / prelim" → b_gse`), replacing whatever prior
  coverage existed (if any) for the old broken candidate paths.

## Out of scope

- The known, separately-tracked `ConfigEntry.save()` unguarded-teardown
  issue — unrelated, already logged for its own session.
- Any change to the tutorial *engine* itself (dataclasses, registry,
  controller, picker, plugin-registration API) — all unchanged.
- Writing tours for out-of-tree plugins.
