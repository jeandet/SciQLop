# Onboarding: fix broken product target + merge 3 tours into 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken `plot_product` onboarding step (wrong tree path, always times out) and merge the three built-in tours (Getting Started, Catalogs, Settings) into a single 11-step "Getting Started" tour.

**Architecture:** No changes to the tour engine (`tour.py`, `registry.py`, `tour_controller.py`, `tour_picker.py`). `tour_catalogs.py`/`tour_settings.py` stop building/registering their own `Tour` and instead export a plain `list[TourStep]`; `tour_getting_started.py` concatenates all three step groups into one `Tour` and is the only module left calling `register_tour`.

**Tech Stack:** Python, pytest, pytest-qt (existing test conventions in `tests/test_onboarding_*.py`).

## Global Constraints

- Run all commands with `uv run` (e.g. `uv run pytest`).
- Follow TDD: write the failing test first, confirm it fails, then implement.
- `Tour`/`TourStep` stay frozen dataclasses — no change to `tour.py`.
- `GETTING_STARTED` keeps `id="getting_started"` and `title="Getting Started"` — `mainwindow.py` (lines 194-195, 618-621) references this id directly and must not need edits.
- The verified real product path is exactly:
  `["speasy", "amda", "Parameters", "ACE", "MFI", "final / prelim", "b_gse"]`
  (`"final / prelim"` is one tree node, not two).
- Final step order for the merged tour:
  `create_panel, open_products, plot_product, overlay_vs_new_subplot, shortcut_tip, open_catalogs, create_catalog, add_event, overlay_catalog, open_settings, browse_categories`

---

### Task 1: Fix `CANDIDATE_PRODUCT_PATHS` to the real speasy tree path

**Files:**
- Modify: `SciQLop/components/onboarding/backend/targets.py:4-8`
- Test: `tests/test_onboarding_targets.py`

**Interfaces:**
- Consumes: existing `find_index_by_path(model, path, parent=None)` (unchanged signature, `tests/test_onboarding_targets.py:5-35` already has a `_fake_model(tree: dict)` helper building a minimal `QAbstractItemModel`-like mock from a nested dict).
- Produces: `CANDIDATE_PRODUCT_PATHS: list[list[str]]` — consumed unchanged by `resolve_first_candidate_product` (`targets.py:61-77`) and by Task 4's tour assembly (no direct reference, but Task 4's `plot_product` step keeps using `targets.resolve_first_candidate_product` as-is).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_onboarding_targets.py`, right after `test_find_index_by_path_case_insensitive` (currently ending at line 57):

```python
def test_find_index_by_path_matches_the_real_ace_mfi_candidate_path():
    from SciQLop.components.onboarding.backend.targets import (
        find_index_by_path, CANDIDATE_PRODUCT_PATHS,
    )
    model = _fake_model({
        "speasy": {"amda": {"Parameters": {"ACE": {"MFI": {
            "final / prelim": {"b_gse": {}},
        }}}}},
    })
    result = find_index_by_path(model, CANDIDATE_PRODUCT_PATHS[0])
    assert result is not None
    assert result._name == "b_gse"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboarding_targets.py::test_find_index_by_path_matches_the_real_ace_mfi_candidate_path -v`
Expected: FAIL — `CANDIDATE_PRODUCT_PATHS[0]` is currently `["cda", "MMS", "MMS1", "FGM", "mms1_fgm_b_gse_srvy_l2"]`, which doesn't match anything in this fake tree, so `result is None` and the `assert result is not None` fails.

- [ ] **Step 3: Fix `CANDIDATE_PRODUCT_PATHS`**

In `SciQLop/components/onboarding/backend/targets.py`, replace lines 4-8:

```python
CANDIDATE_PRODUCT_PATHS: list[list[str]] = [
    ["cda", "MMS", "MMS1", "FGM", "mms1_fgm_b_gse_srvy_l2"],
    ["cda", "THEMIS", "THA", "FGM", "tha_fgs_gse"],
    ["amda", "Parameters", "Clusters", "Cluster1", "Ephemeris", "c1_xyz_gse"],
]
```

with:

```python
CANDIDATE_PRODUCT_PATHS: list[list[str]] = [
    ["speasy", "amda", "Parameters", "ACE", "MFI", "final / prelim", "b_gse"],
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_onboarding_targets.py -v`
Expected: all tests in the file PASS, including the new one.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/onboarding/backend/targets.py tests/test_onboarding_targets.py
git commit -m "fix(onboarding): target the real speasy-rooted ACE/MFI/b_gse path

CANDIDATE_PRODUCT_PATHS assumed provider names were top-level tree
rows, but the tree is rooted at a single 'speasy' node. Every
candidate always failed to resolve, so the plot_product step polled
for its full 10s timeout and TourController.abort() silently ended
the tour right after the Products browser opened."
```

---

### Task 2: Convert `tour_catalogs.py` to export a step list instead of a registered `Tour`

**Files:**
- Modify: `SciQLop/components/onboarding/backend/tour_catalogs.py` (full file, 57 lines)
- Test: `tests/test_onboarding_tour_catalogs.py` (full file, 30 lines)

**Interfaces:**
- Consumes: `TourStep` from `SciQLop.components.onboarding.backend.tour` (unchanged), `targets`/`completions` modules (unchanged).
- Produces: `CATALOGS_STEPS: list[TourStep]` — consumed by Task 4 (`tour_getting_started.py` imports this name).

- [ ] **Step 1: Write the failing test**

Replace the full contents of `tests/test_onboarding_tour_catalogs.py`:

```python
def test_catalogs_has_four_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    assert [s.step_id for s in CATALOGS_STEPS] == [
        "open_catalogs", "create_catalog", "add_event", "overlay_catalog",
    ]


def test_add_event_and_overlay_steps_poll_with_timeout():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    for step_id in ("add_event", "overlay_catalog"):
        assert by_id[step_id].poll is True
        assert by_id[step_id].timeout_s is not None
        assert by_id[step_id].timeout_message is not None
    for step_id in ("open_catalogs", "create_catalog"):
        assert by_id[step_id].poll is False


def test_only_open_catalogs_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["open_catalogs"].completion is not None
    for step_id in ("create_catalog", "add_event", "overlay_catalog"):
        assert by_id[step_id].completion is None
```

(This drops the old `test_catalogs_is_registered` — `tour_catalogs.py` no longer registers anything on its own after Step 3.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboarding_tour_catalogs.py -v`
Expected: FAIL with `ImportError: cannot import name 'CATALOGS_STEPS'` (the module currently exports `CATALOGS`, a `Tour`, not `CATALOGS_STEPS`).

- [ ] **Step 3: Rename `CATALOGS` to `CATALOGS_STEPS`, drop the `Tour` wrapper and registration**

Replace the full contents of `SciQLop/components/onboarding/backend/tour_catalogs.py`:

```python
from SciQLop.components.onboarding.backend.tour import TourStep
from SciQLop.components.onboarding.backend import targets, completions

_NO_CATALOG_MESSAGE = (
    "Create or select a catalog to see event controls — replay this tour "
    "anytime from Tools → Take a Tour."
)
_NO_PANEL_MESSAGE = (
    "Plot something first to see how overlaying catalogs works — replay "
    "this tour anytime from Tools → Take a Tour."
)

CATALOGS_STEPS: list[TourStep] = [
    TourStep(
        step_id="open_catalogs",
        title="Find the Catalogs browser",
        body="Your labeled time intervals live here — click to open the Catalogs browser.",
        resolver=targets.side_tab_resolver("Catalog Browser"),
        completion=completions.dock_visible("Catalog Browser"),
    ),
    TourStep(
        step_id="create_catalog",
        title="Create a catalog",
        body="Right-click a provider here to create a new catalog.",
        resolver=targets.resolve_catalog_tree,
    ),
    TourStep(
        step_id="add_event",
        title="Label a time interval",
        body="Select a catalog, then click 'Add Event' to label a time interval.",
        resolver=targets.resolve_add_event_button,
        poll=True,
        timeout_s=15.0,
        timeout_message=_NO_CATALOG_MESSAGE,
    ),
    TourStep(
        step_id="overlay_catalog",
        title="Overlay a catalog on a plot",
        body=(
            "Drag a catalog onto a graph to overlay it there, or "
            "right-click a panel → Catalogs to toggle one on or off."
        ),
        resolver=targets.resolve_any_plot_with_data,
        poll=True,
        timeout_s=15.0,
        timeout_message=_NO_PANEL_MESSAGE,
    ),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_onboarding_tour_catalogs.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/onboarding/backend/tour_catalogs.py tests/test_onboarding_tour_catalogs.py
git commit -m "refactor(onboarding): tour_catalogs exports CATALOGS_STEPS, not a registered Tour"
```

---

### Task 3: Convert `tour_settings.py` to export a step list instead of a registered `Tour`

**Files:**
- Modify: `SciQLop/components/onboarding/backend/tour_settings.py` (full file, 30 lines)
- Test: `tests/test_onboarding_tour_settings.py` (full file, 15 lines)

**Interfaces:**
- Consumes: `TourStep`, `targets`/`completions` (unchanged).
- Produces: `SETTINGS_STEPS: list[TourStep]` — consumed by Task 4.

- [ ] **Step 1: Write the failing test**

Replace the full contents of `tests/test_onboarding_tour_settings.py`:

```python
def test_settings_has_two_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS_STEPS
    assert [s.step_id for s in SETTINGS_STEPS] == ["open_settings", "browse_categories"]


def test_only_open_settings_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS_STEPS
    by_id = {s.step_id: s for s in SETTINGS_STEPS}
    assert by_id["open_settings"].completion is not None
    assert by_id["browse_categories"].completion is None
```

(Drops the old `test_settings_is_registered`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboarding_tour_settings.py -v`
Expected: FAIL with `ImportError: cannot import name 'SETTINGS_STEPS'`.

- [ ] **Step 3: Rename `SETTINGS` to `SETTINGS_STEPS`, drop the `Tour` wrapper and registration**

Replace the full contents of `SciQLop/components/onboarding/backend/tour_settings.py`:

```python
from SciQLop.components.onboarding.backend.tour import TourStep
from SciQLop.components.onboarding.backend import targets, completions

SETTINGS_STEPS: list[TourStep] = [
    TourStep(
        step_id="open_settings",
        title="Find Settings",
        body="Click here to open Settings.",
        resolver=targets.side_tab_resolver("Settings"),
        completion=completions.dock_visible("Settings"),
    ),
    TourStep(
        step_id="browse_categories",
        title="Browse categories",
        body=(
            "Settings are organized by category — try Appearance for "
            "instant visual feedback, or Plugins/Workspaces to manage "
            "what's loaded."
        ),
        resolver=targets.resolve_settings_category_list,
    ),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_onboarding_tour_settings.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/onboarding/backend/tour_settings.py tests/test_onboarding_tour_settings.py
git commit -m "refactor(onboarding): tour_settings exports SETTINGS_STEPS, not a registered Tour"
```

---

### Task 4: Merge all steps into `GETTING_STARTED` and slim `register_builtin_tours`

**Files:**
- Modify: `SciQLop/components/onboarding/backend/tour_getting_started.py` (full file, 62 lines)
- Modify: `SciQLop/components/onboarding/backend/registry.py:25-31`
- Test: `tests/test_onboarding_tour_getting_started.py` (full file, 34 lines)

**Interfaces:**
- Consumes: `CATALOGS_STEPS` (Task 2), `SETTINGS_STEPS` (Task 3), existing `targets`/`completions`.
- Produces: `GETTING_STARTED: Tour` with `id="getting_started"` and 11 steps — this is the only `Tour` any built-in module registers after this task. `mainwindow.py` and `tour_controller.py` need no changes (both already reference tours generically by id/registry).

- [ ] **Step 1: Write the failing test**

Replace the full contents of `tests/test_onboarding_tour_getting_started.py`:

```python
def test_getting_started_has_eleven_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    assert [s.step_id for s in GETTING_STARTED.steps] == [
        "create_panel", "open_products", "plot_product",
        "overlay_vs_new_subplot", "shortcut_tip",
        "open_catalogs", "create_catalog", "add_event", "overlay_catalog",
        "open_settings", "browse_categories",
    ]


def test_polling_steps_have_timeouts():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    polling_steps = {"plot_product", "add_event", "overlay_catalog"}
    for step_id, step in by_id.items():
        if step_id in polling_steps:
            assert step.poll is True
            assert step.timeout_s is not None
            assert step.timeout_message is not None
        else:
            assert step.poll is False
            assert step.timeout_s is None


def test_tip_only_steps_have_no_completion():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    no_completion_steps = {
        "overlay_vs_new_subplot", "shortcut_tip",
        "create_catalog", "add_event", "overlay_catalog", "browse_categories",
    }
    has_completion_steps = {
        "create_panel", "open_products", "plot_product",
        "open_catalogs", "open_settings",
    }
    for step_id in no_completion_steps:
        assert by_id[step_id].completion is None
    for step_id in has_completion_steps:
        assert by_id[step_id].completion is not None


def test_getting_started_is_registered():
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    registry.register_builtin_tours()
    assert registry.get_tour("getting_started") is GETTING_STARTED


def test_only_getting_started_is_registered_as_a_builtin_tour():
    from SciQLop.components.onboarding.backend import registry
    registry.register_builtin_tours()
    assert {t.id for t in registry.all_tours()} == {"getting_started"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboarding_tour_getting_started.py -v`
Expected: FAIL — `test_getting_started_has_eleven_steps_in_order` fails because `GETTING_STARTED.steps` currently has only 5 step ids; `test_only_getting_started_is_registered_as_a_builtin_tour` fails because `all_tours()` currently also contains `"catalogs"` and `"settings"`.

Note: run this file in isolation (`pytest tests/test_onboarding_tour_getting_started.py`) — the process-wide `_registry` means running it after Tasks 2/3's test files (which no longer register `"catalogs"`/`"settings"`) in the same session would already show a smaller registry; running it standalone here keeps this step's before/after comparison unambiguous.

- [ ] **Step 3: Concatenate the steps in `tour_getting_started.py`**

Replace the full contents of `SciQLop/components/onboarding/backend/tour_getting_started.py`:

```python
from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import register_tour
from SciQLop.components.onboarding.backend import targets, completions
from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
from SciQLop.components.onboarding.backend.tour_settings import SETTINGS_STEPS

_OFFLINE_MESSAGE = (
    "Looks like data providers aren't ready yet — replay this tour anytime "
    "from Tools → Take a Tour once you're online."
)

GETTING_STARTED = Tour(
    id="getting_started",
    title="Getting Started",
    description=(
        "Create your first plot panel, plot a real product, browse "
        "catalogs, and find your way around Settings."
    ),
    steps=[
        TourStep(
            step_id="create_panel",
            title="Create your first plot panel",
            body="Click here to create your first plot panel.",
            resolver=targets.resolve_add_panel_button,
            completion=completions.panel_created,
        ),
        TourStep(
            step_id="open_products",
            title="Find the Products browser",
            body="Your data lives here — click to open the Products browser.",
            resolver=targets.side_tab_resolver("Products"),
            completion=completions.dock_visible("Products"),
        ),
        TourStep(
            step_id="plot_product",
            title="Plot a real product",
            body="Drag this onto your empty panel to plot it.",
            resolver=targets.resolve_first_candidate_product,
            poll=True,
            completion=completions.plot_added_to("create_panel"),
            timeout_s=10.0,
            timeout_message=_OFFLINE_MESSAGE,
        ),
        TourStep(
            step_id="overlay_vs_new_subplot",
            title="Adding more data",
            body=(
                "Adding more data: drop a product in the middle of a graph to "
                "overlay it there, or near its top/bottom edge (watch for the "
                "blue highlight) to stack it as a new plot in this panel."
            ),
            resolver=targets.resolve_latest_plot_widget,
        ),
        TourStep(
            step_id="shortcut_tip",
            title="One-click shortcut",
            body=(
                "Tip: next time, right-click any product → '+ New panel' "
                "to create a panel and plot it in one click."
            ),
            resolver=targets.resolve_products_tree_widget,
        ),
        *CATALOGS_STEPS,
        *SETTINGS_STEPS,
    ],
)

register_tour(GETTING_STARTED)
```

- [ ] **Step 4: Slim `register_builtin_tours` in `registry.py`**

In `SciQLop/components/onboarding/backend/registry.py`, replace lines 25-31:

```python
def register_builtin_tours() -> None:
    """Import every built-in tour module -- each registers itself as a
    module-level side effect. Safe to call more than once: Python only
    executes a module body on its first import."""
    from SciQLop.components.onboarding.backend import (  # noqa: F401
        tour_getting_started, tour_catalogs, tour_settings,
    )
```

with:

```python
def register_builtin_tours() -> None:
    """Import the built-in tour module -- it registers itself as a
    module-level side effect (and transitively imports tour_catalogs/
    tour_settings for their step lists, which no longer self-register).
    Safe to call more than once: Python only executes a module body on
    its first import."""
    from SciQLop.components.onboarding.backend import tour_getting_started  # noqa: F401
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_onboarding_tour_getting_started.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add SciQLop/components/onboarding/backend/tour_getting_started.py \
        SciQLop/components/onboarding/backend/registry.py \
        tests/test_onboarding_tour_getting_started.py
git commit -m "feat(onboarding): merge Catalogs and Settings steps into the Getting Started tour

One continuous 11-step tour now covers plotting, catalogs, and
settings instead of three separately-launched tours. Keeps
id=\"getting_started\" so mainwindow.py's auto-run and picker code
need no changes."
```

---

### Task 5: Update the tour picker tests for the single merged tour

**Files:**
- Modify: `tests/test_onboarding_tour_picker.py` (full file, 51 lines)

**Interfaces:**
- Consumes: `TourPicker` (`SciQLop/components/onboarding/ui/tour_picker.py`, unchanged), `register_builtin_tours`/`all_tours` (Task 4's registry behavior), `OnboardingSettings` (unchanged).
- Produces: nothing consumed by later tasks — this is the last task.

- [ ] **Step 1: Write the updated tests**

Replace the full contents of `tests/test_onboarding_tour_picker.py`:

```python
from .fixtures import *


def test_picker_lists_all_registered_tours(main_window):
    from SciQLop.components.onboarding.ui.tour_picker import TourPicker
    from SciQLop.components.onboarding.backend.registry import register_builtin_tours, all_tours

    register_builtin_tours()
    picker = TourPicker(main_window)
    try:
        registered_ids = {tour.id for tour in all_tours()}
        assert set(picker._items_by_tour_id.keys()) == registered_ids
        assert registered_ids == {"getting_started"}
    finally:
        picker.close()


def test_picker_marks_completed_tours(main_window):
    from SciQLop.components.onboarding.ui.tour_picker import TourPicker
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {"getting_started": True}

    picker = TourPicker(main_window)
    try:
        assert "Completed" in picker._items_by_tour_id["getting_started"].text()
    finally:
        picker.close()
        with OnboardingSettings() as s:
            s.completed_tours = {}


def test_start_selected_starts_the_selected_tour(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_picker import TourPicker
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}
    main_window._onboarding_controller = None

    picker = TourPicker(main_window)
    picker._list.setCurrentItem(picker._items_by_tour_id["getting_started"])
    picker._start_selected()

    try:
        qtbot.waitUntil(
            lambda: main_window._onboarding_controller is not None
            and main_window._onboarding_controller._tour.id == "getting_started",
            timeout=1000)
    finally:
        main_window._onboarding_controller.abort()


def test_start_selected_with_no_selection_does_nothing(main_window):
    from SciQLop.components.onboarding.ui.tour_picker import TourPicker

    main_window._onboarding_controller = None
    picker = TourPicker(main_window)
    try:
        picker._list.setCurrentItem(None)
        picker._start_selected()
        assert main_window._onboarding_controller is None
    finally:
        picker.close()
```

- [ ] **Step 2: Run test to verify behavior**

Run: `uv run pytest tests/test_onboarding_tour_picker.py -v`
Expected: all 4 tests PASS. (Not a red/green TDD step in the usual sense — these tests exercise pre-existing generic picker behavior against the now-single-tour registry state established by Task 4; if any fails, re-check that Task 4's Step 4 change actually reduced `all_tours()` to one entry.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_onboarding_tour_picker.py
git commit -m "test(onboarding): update tour picker tests for the single merged tour"
```

---

### Task 6: Full suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full onboarding test slice**

Run: `uv run pytest tests/test_onboarding_targets.py tests/test_onboarding_tour_catalogs.py tests/test_onboarding_tour_settings.py tests/test_onboarding_tour_getting_started.py tests/test_onboarding_tour_picker.py tests/test_onboarding_plugin_api.py -v`
Expected: every test PASSES. Read the actual pass count from the summary line — don't infer success from partial output.

- [ ] **Step 2: Run the full project test suite**

Run: `uv run pytest --no-xvfb`
Expected: same pass/fail count as the pre-change baseline plus the new/changed onboarding tests, all passing. Read the actual exit code and final summary line.

- [ ] **Step 3: Manual smoke check (optional but recommended for a UI change)**

Run: `uv run sciqlop`, open Tools → Take a Tour, confirm exactly one entry ("Getting Started") is listed, start it, and confirm the `plot_product` step now highlights and successfully waits for a drag-drop of the ACE/MFI b_gse row instead of timing out.
