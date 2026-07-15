# Onboarding Tutorial Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the single-sequence onboarding tour into a multi-tour engine — a `Tour`/`TourStep` registry, a "Take a Tour" picker dialog, two new built-in tours (Catalogs, Settings), and a `register_tour()` API any out-of-tree plugin can call from its own `load(main_window)` to add a tour without touching SciQLop core.

**Architecture:** `TourStep`/`Tour` become frozen dataclasses whose `resolver`/`completion` fields hold direct Python callables (not string ids looked up in a shared dict) — this is what lets `TourController` become fully generic with zero tour-specific branching. A module-level registry (`register_tour`/`get_tour`/`all_tours`) is the single source of truth both built-in and plugin tours register into. A generic `context: dict` on the controller replaces the old one-off `self._panel_from_step_1` attribute, accumulating each completed step's result automatically so later steps' resolvers can read earlier ones.

**Tech Stack:** PySide6/Qt6, pytest-qt, existing `SciQLop/components/onboarding/` component.

## Global Constraints

- Every new/changed file lives under `SciQLop/components/onboarding/` (backend or ui) or is a small, precise diff to `SciQLop/core/ui/mainwindow.py`. No out-of-tree plugin repo is touched in this plan.
- `TourStep`/`Tour` are plain `@dataclass(frozen=True)`, not Pydantic (see spec's "Decisions carried in from discussion").
- `OnboardingSettings.tour_completed: bool` becomes `completed_tours: Dict[str, bool]`. Not migrated — this is intentional, do not add migration code.
- Every resolver/completion callable has the exact signature `(main_window, context) -> object | None`. No exceptions, no optional-arg variants — the controller calls all of them uniformly.
- Run tests with `uv run pytest <path> --no-xvfb` per this repo's canonical local test command.
- Follow `docs/qt-lifetime-patterns.md` for any signal wiring: never touch a parent from a slot wired to a child's `destroyed` signal.
- Full design context: `docs/superpowers/specs/2026-07-15-onboarding-tutorial-engine-design.md`. Read it before starting Task 1 if anything below is unclear.

---

## Task 1: Engine core — data model, registry, generalized controller, ported Getting Started tour

This is the one genuinely atomic unit of this plan: the new `TourStep`/`Tour` shape, the registry, the generalized controller, and the ported Getting-Started tour content are not independently meaningful — the controller can't run without the new data shape, and the data shape is pointless without a controller that consumes it. All of it lands together so `main_window`-fixture-dependent tests (used across the whole suite, not just onboarding) keep passing at the end of this task.

**Files:**
- Modify: `SciQLop/components/onboarding/backend/tour.py` (replace entirely)
- Create: `SciQLop/components/onboarding/backend/registry.py`
- Create: `SciQLop/components/onboarding/backend/completions.py`
- Modify: `SciQLop/components/onboarding/backend/targets.py`
- Create: `SciQLop/components/onboarding/backend/tour_getting_started.py`
- Modify: `SciQLop/components/onboarding/ui/tour_controller.py` (replace entirely)
- Modify: `SciQLop/components/onboarding/__init__.py`
- Test: `tests/test_onboarding_registry.py` (new, replaces `tests/test_onboarding_tour_steps.py`)
- Test: `tests/test_onboarding_targets.py` (extend)
- Test: `tests/test_onboarding_tour_controller.py` (replace entirely)
- Delete: `tests/test_onboarding_tour_steps.py`

**Interfaces:**
- Produces (used by every later task): `Tour`, `TourStep` (from `backend/tour.py`); `register_tour(tour)`, `get_tour(tour_id) -> Tour | None`, `all_tours() -> list[Tour]`, `register_builtin_tours()` (from `backend/registry.py`); `panel_created`, `dock_visible(dock_name)`, `plot_added_to(context_key)` (from `backend/completions.py`); `resolve_add_panel_button`, `resolve_first_candidate_product`, `resolve_products_tree_widget`, `resolve_latest_plot_widget`, `side_tab_resolver(dock_name)` (from `backend/targets.py`, all now `(main_window, context)`); `GETTING_STARTED: Tour` (from `backend/tour_getting_started.py`); `TourController(main_window, tour)`, `run_tour(main_window, tour_id) -> TourController | None` (from `ui/tour_controller.py`).
- Consumes: nothing new from other tasks (this task is the foundation).

### Step 1: Write the failing test for `Tour`/`TourStep`/registry

Create `tests/test_onboarding_registry.py`:

```python
import pytest


def _make_step(step_id="step", resolver=None, completion=None, **kwargs):
    from SciQLop.components.onboarding.backend.tour import TourStep
    return TourStep(
        step_id=step_id,
        title=f"{step_id} title",
        body=f"{step_id} body",
        resolver=resolver or (lambda main_window, context: None),
        completion=completion,
        **kwargs,
    )


def _make_tour(tour_id="fake_tour", steps=None):
    from SciQLop.components.onboarding.backend.tour import Tour
    return Tour(
        id=tour_id, title="Fake Tour", description="A fake tour for tests.",
        steps=steps or [_make_step()],
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    from SciQLop.components.onboarding.backend import registry
    yield
    registry._forget_tour_for_tests("fake_tour")
    registry._forget_tour_for_tests("fake_tour_2")


def test_tour_step_is_frozen():
    step = _make_step()
    with pytest.raises(Exception):
        step.title = "changed"


def test_register_tour_then_get_tour_round_trips():
    from SciQLop.components.onboarding.backend import registry
    tour = _make_tour()
    registry.register_tour(tour)
    assert registry.get_tour("fake_tour") is tour


def test_get_tour_returns_none_for_unknown_id():
    from SciQLop.components.onboarding.backend import registry
    assert registry.get_tour("no_such_tour") is None


def test_register_tour_rejects_duplicate_id():
    from SciQLop.components.onboarding.backend import registry
    registry.register_tour(_make_tour())
    with pytest.raises(ValueError, match="already registered"):
        registry.register_tour(_make_tour())


def test_register_tour_rejects_empty_steps():
    from SciQLop.components.onboarding.backend import registry
    with pytest.raises(ValueError, match="no steps"):
        registry.register_tour(_make_tour(steps=[]))


def test_all_tours_reflects_registrations():
    from SciQLop.components.onboarding.backend import registry
    before = {t.id for t in registry.all_tours()}
    registry.register_tour(_make_tour("fake_tour"))
    registry.register_tour(_make_tour("fake_tour_2"))
    after = {t.id for t in registry.all_tours()}
    assert after - before == {"fake_tour", "fake_tour_2"}
```

### Step 2: Run the test to verify it fails

Run: `uv run pytest tests/test_onboarding_registry.py -v --no-xvfb`
Expected: FAIL — `ModuleNotFoundError` or `ImportError` (`backend.registry` doesn't exist yet, `Tour`/`TourStep` don't have the new shape).

### Step 3: Rewrite `backend/tour.py`

```python
from dataclasses import dataclass
from typing import Callable, Any

TargetResolver = Callable[[Any, dict], object | None]
CompletionResolver = Callable[[Any, dict], object | None]


@dataclass(frozen=True)
class TourStep:
    step_id: str
    title: str
    body: str
    resolver: TargetResolver
    completion: CompletionResolver | None = None
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

### Step 4: Create `backend/registry.py`

```python
from SciQLop.components.onboarding.backend.tour import Tour

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


def register_builtin_tours() -> None:
    """Import every built-in tour module -- each registers itself as a
    module-level side effect. Safe to call more than once: Python only
    executes a module body on its first import."""
    from SciQLop.components.onboarding.backend import tour_getting_started  # noqa: F401


def _forget_tour_for_tests(tour_id: str) -> None:
    _registry.pop(tour_id, None)


def _reset_registry_for_tests() -> None:
    _registry.clear()
```

### Step 5: Run the test to verify it passes

Run: `uv run pytest tests/test_onboarding_registry.py -v --no-xvfb`
Expected: PASS (7 tests).

### Step 6: Commit

```bash
git add SciQLop/components/onboarding/backend/tour.py \
        SciQLop/components/onboarding/backend/registry.py \
        tests/test_onboarding_registry.py
git commit -m "feat(onboarding): add Tour/TourStep data model and registry"
```

### Step 7: Write the failing test for `completions.py`

Create `tests/test_onboarding_completions.py`:

```python
from .fixtures import *


def test_panel_created_returns_panel_added_signal(main_window):
    from SciQLop.components.onboarding.backend.completions import panel_created
    assert panel_created(main_window, {}) is main_window.panel_added


def test_dock_visible_returns_none_when_dock_missing(main_window):
    from SciQLop.components.onboarding.backend.completions import dock_visible
    result = dock_visible("No Such Dock")(main_window, {})
    assert result is None


def test_dock_visible_predicate_filters_on_true(main_window):
    from SciQLop.components.onboarding.backend.completions import dock_visible
    signal, predicate = dock_visible("Products")(main_window, {})
    assert signal is main_window.dock_manager.findDockWidget("Products").visibilityChanged
    assert predicate(True) is True
    assert predicate(False) is False


def test_plot_added_to_reads_panel_from_context(main_window):
    from SciQLop.components.onboarding.backend.completions import plot_added_to
    fake_panel = type("FakePanel", (), {"plot_added": "sentinel"})()
    context = {"create_panel": fake_panel}
    assert plot_added_to("create_panel")(main_window, context) == "sentinel"


def test_plot_added_to_returns_none_when_context_key_missing():
    from SciQLop.components.onboarding.backend.completions import plot_added_to
    assert plot_added_to("create_panel")(None, {}) is None
```

### Step 8: Run the test to verify it fails

Run: `uv run pytest tests/test_onboarding_completions.py -v --no-xvfb`
Expected: FAIL — `ModuleNotFoundError: No module named '...backend.completions'`.

### Step 9: Create `backend/completions.py`

```python
def panel_created(main_window, context):
    return main_window.panel_added


def dock_visible(dock_name):
    def _completion(main_window, context):
        dw = main_window.dock_manager.findDockWidget(dock_name)
        if dw is None:
            return None
        return dw.visibilityChanged, (lambda visible: visible)
    return _completion


def plot_added_to(context_key):
    def _completion(main_window, context):
        panel = context.get(context_key)
        if panel is None:
            return None
        return panel.plot_added
    return _completion
```

### Step 10: Run the test to verify it passes

Run: `uv run pytest tests/test_onboarding_completions.py -v --no-xvfb`
Expected: PASS (5 tests).

### Step 11: Commit

```bash
git add SciQLop/components/onboarding/backend/completions.py \
        tests/test_onboarding_completions.py
git commit -m "feat(onboarding): add completion-signal factory functions"
```

### Step 12: Write the failing test for updated `targets.py`

Extend `tests/test_onboarding_targets.py` — add at the end of the file (keep the existing `find_index_by_path` tests untouched above):

```python
from .fixtures import *


def test_resolve_add_panel_button_accepts_context_arg(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button
    # Must not raise TypeError for the extra positional arg.
    resolve_add_panel_button(main_window, {})


def test_resolve_products_tree_widget_accepts_context_arg(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_products_tree_widget
    resolve_products_tree_widget(main_window, {})


def test_resolve_first_candidate_product_accepts_context_arg(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_first_candidate_product
    resolve_first_candidate_product(main_window, {})


def test_resolve_latest_plot_widget_reads_panel_from_context(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_latest_plot_widget
    assert resolve_latest_plot_widget(main_window, {}) is None

    fake_panel = type("FakePanel", (), {"plots": lambda self: []})()
    assert resolve_latest_plot_widget(main_window, {"create_panel": fake_panel}) is None

    fake_widget = object()
    fake_panel_with_plot = type("FakePanel", (), {"plots": lambda self: [fake_widget]})()
    assert resolve_latest_plot_widget(
        main_window, {"create_panel": fake_panel_with_plot}) is fake_widget


def test_side_tab_resolver_returns_none_for_missing_dock(main_window):
    from SciQLop.components.onboarding.backend.targets import side_tab_resolver
    assert side_tab_resolver("No Such Dock")(main_window, {}) is None


def test_side_tab_resolver_returns_products_side_tab(main_window):
    from SciQLop.components.onboarding.backend.targets import side_tab_resolver
    dw = main_window.dock_manager.findDockWidget("Products")
    assert side_tab_resolver("Products")(main_window, {}) is dw.sideTabWidget()
```

### Step 13: Run the test to verify it fails

Run: `uv run pytest tests/test_onboarding_targets.py -v --no-xvfb`
Expected: FAIL — `TypeError: resolve_add_panel_button() takes 1 positional argument but 2 were given` (and `ImportError` for `side_tab_resolver`, `resolve_latest_plot_widget` still expecting `panel` not `context`).

### Step 14: Rewrite `backend/targets.py`

```python
from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex
from PySide6.QtWidgets import QTreeView, QWidget

CANDIDATE_PRODUCT_PATHS: list[list[str]] = [
    ["cda", "MMS", "MMS1", "FGM", "mms1_fgm_b_gse_srvy_l2"],
    ["cda", "THEMIS", "THA", "FGM", "tha_fgs_gse"],
    ["amda", "Parameters", "Clusters", "Cluster1", "Ephemeris", "c1_xyz_gse"],
]


def find_index_by_path(model: QAbstractItemModel, path: list[str],
                        parent: QModelIndex | None = None) -> QModelIndex | None:
    if not path:
        return parent
    parent = parent if parent is not None else QModelIndex()
    row_count = model.rowCount(parent)
    target = path[0].lower()
    for row in range(row_count):
        idx = model.index(row, 0, parent)
        text = model.data(idx, Qt.ItemDataRole.DisplayRole)
        if isinstance(text, str) and text.lower() == target:
            return find_index_by_path(model, path[1:], idx)
    return None


def _products_tree_view(main_window) -> QTreeView | None:
    trees = main_window.productTree.findChildren(QTreeView)
    return trees[0] if trees else None


def resolve_add_panel_button(main_window, context) -> QWidget | None:
    dw = next((dw for dw in main_window.dock_manager.dockWidgets()
               if dw.widget() is main_window.welcome), None)
    if dw is None:
        return None
    area = dw.dockAreaWidget()
    if area is None:
        return None
    return area.property("sciqlop_add_panel_button")


def side_tab_resolver(dock_name: str):
    def _resolver(main_window, context) -> QWidget | None:
        dw = main_window.dock_manager.findDockWidget(dock_name)
        if dw is None:
            return None
        return dw.sideTabWidget()
    return _resolver


def _expand_ancestors(tree: QTreeView, index: QModelIndex) -> None:
    parent = index.parent()
    chain = []
    while parent.isValid():
        chain.append(parent)
        parent = parent.parent()
    for ancestor in reversed(chain):
        tree.setExpanded(ancestor, True)


def resolve_first_candidate_product(main_window, context):
    """Returns (tree, rect) where rect is the matched row's visualRect in
    the tree's own local coordinates -- CoachMark highlights that sub-region
    of the tree widget rather than the whole tree."""
    tree = _products_tree_view(main_window)
    if tree is None:
        return None
    model = tree.model()
    if model is None:
        return None
    for path in CANDIDATE_PRODUCT_PATHS:
        index = find_index_by_path(model, path)
        if index is not None:
            _expand_ancestors(tree, index)
            tree.scrollTo(index)
            return tree, tree.visualRect(index)
    return None


def resolve_latest_plot_widget(main_window, context) -> QWidget | None:
    panel = context.get("create_panel")
    if panel is None:
        return None
    plots = panel.plots()
    return plots[-1] if plots else None


def resolve_products_tree_widget(main_window, context) -> QWidget | None:
    return _products_tree_view(main_window)
```

Note: the module-level `RESOLVERS` dict is deleted -- nothing looks resolvers
up by string id anymore, tours hold direct function references.

### Step 15: Run the test to verify it passes

Run: `uv run pytest tests/test_onboarding_targets.py -v --no-xvfb`
Expected: PASS (all tests, old `find_index_by_path` tests plus the new ones).

### Step 16: Commit

```bash
git add SciQLop/components/onboarding/backend/targets.py \
        tests/test_onboarding_targets.py
git commit -m "refactor(onboarding): resolvers take (main_window, context), add side_tab_resolver"
```

### Step 17: Write the failing test for the ported Getting Started tour

Create `tests/test_onboarding_tour_getting_started.py`:

```python
def test_getting_started_has_five_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    assert [s.step_id for s in GETTING_STARTED.steps] == [
        "create_panel", "open_products", "plot_product",
        "overlay_vs_new_subplot", "shortcut_tip",
    ]


def test_only_plot_product_step_polls_with_timeout():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    assert by_id["plot_product"].poll is True
    assert by_id["plot_product"].timeout_s == 10.0
    assert by_id["plot_product"].timeout_message is not None
    for step_id in ("create_panel", "open_products",
                     "overlay_vs_new_subplot", "shortcut_tip"):
        assert by_id[step_id].poll is False
        assert by_id[step_id].timeout_s is None


def test_tip_only_steps_have_no_completion():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    assert by_id["overlay_vs_new_subplot"].completion is None
    assert by_id["shortcut_tip"].completion is None
    assert by_id["create_panel"].completion is not None
    assert by_id["open_products"].completion is not None
    assert by_id["plot_product"].completion is not None


def test_getting_started_is_registered():
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    registry.register_builtin_tours()
    assert registry.get_tour("getting_started") is GETTING_STARTED
```

### Step 18: Run the test to verify it fails

Run: `uv run pytest tests/test_onboarding_tour_getting_started.py -v --no-xvfb`
Expected: FAIL — `ModuleNotFoundError`.

### Step 19: Create `backend/tour_getting_started.py`

```python
from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import register_tour
from SciQLop.components.onboarding.backend import targets, completions

_OFFLINE_MESSAGE = (
    "Looks like data providers aren't ready yet — replay this tour anytime "
    "from Tools → Take a Tour once you're online."
)

GETTING_STARTED = Tour(
    id="getting_started",
    title="Getting Started",
    description="Create your first plot panel and plot a real product.",
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
    ],
)

register_tour(GETTING_STARTED)
```

### Step 20: Run the test to verify it passes

Run: `uv run pytest tests/test_onboarding_tour_getting_started.py -v --no-xvfb`
Expected: PASS (4 tests).

### Step 21: Delete the superseded test file and commit

```bash
git rm tests/test_onboarding_tour_steps.py
git add SciQLop/components/onboarding/backend/tour_getting_started.py \
        tests/test_onboarding_tour_getting_started.py
git commit -m "feat(onboarding): port Getting Started tour to the new engine shape"
```

### Step 22: Write the failing test for the generalized controller

Replace `tests/test_onboarding_tour_controller.py` entirely:

```python
from .fixtures import *
import pytest


def _make_step(step_id, resolver, completion=None, **kwargs):
    from SciQLop.components.onboarding.backend.tour import TourStep
    return TourStep(
        step_id=step_id, title=f"{step_id} title", body=f"{step_id} body",
        resolver=resolver, completion=completion, **kwargs,
    )


def _make_tour(tour_id, steps):
    from SciQLop.components.onboarding.backend.tour import Tour
    return Tour(id=tour_id, title=tour_id, description="test tour", steps=steps)


def test_start_shows_coach_mark_for_first_step(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    tour = _make_tour("t1", [_make_step("only", lambda mw, ctx: main_window.productTree)])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        assert controller._current_step().step_id == "only"
    finally:
        controller.abort()


def test_dismiss_only_step_advances_on_got_it(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    tour = _make_tour("t2", [
        _make_step("first", lambda mw, ctx: main_window.productTree),
        _make_step("second", lambda mw, ctx: main_window.productTree),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        controller._coach_mark.dismiss_clicked.emit()
        qtbot.waitUntil(lambda: controller._current_step().step_id == "second", timeout=1000)
    finally:
        controller.abort()


def test_completion_signal_advances_and_stores_single_arg_in_context(main_window, qtbot):
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    class _Emitter(QObject):
        fired = Signal(str)

    emitter = _Emitter()
    tour = _make_tour("t3", [
        _make_step("wait_for_it", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: emitter.fired),
        _make_step("after", lambda mw, ctx: main_window.productTree),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        emitter.fired.emit("payload")
        qtbot.waitUntil(lambda: controller._current_step().step_id == "after", timeout=1000)
        assert controller._context["wait_for_it"] == "payload"
    finally:
        controller.abort()


def test_completion_predicate_filters_signal_args(main_window, qtbot):
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    class _Emitter(QObject):
        fired = Signal(bool)

    emitter = _Emitter()
    tour = _make_tour("t4", [
        _make_step("wait_true", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: (emitter.fired, lambda v: v)),
        _make_step("after", lambda mw, ctx: main_window.productTree),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        emitter.fired.emit(False)
        qtbot.wait(100)
        assert controller._current_step().step_id == "wait_true"

        emitter.fired.emit(True)
        qtbot.waitUntil(lambda: controller._current_step().step_id == "after", timeout=1000)
    finally:
        controller.abort()


def test_tuple_target_unpacks_widget_and_rect(main_window, qtbot):
    from PySide6.QtCore import QRect
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    rect = QRect(1, 2, 3, 4)
    tour = _make_tour("t5", [
        _make_step("with_rect", lambda mw, ctx: (main_window.productTree, rect)),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        assert controller._coach_mark._target_local_rect == rect
    finally:
        controller.abort()


def test_later_step_resolver_reads_earlier_step_context(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    def _second_resolver(mw, ctx):
        assert ctx["first"] == "stored"
        return main_window.productTree

    tour = _make_tour("t6", [
        _make_step("first", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: (main_window.panel_added, lambda *a: True)),
        _make_step("second", _second_resolver),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        main_window.panel_added.emit("stored")
        qtbot.waitUntil(lambda: controller._current_step().step_id == "second", timeout=1000)
    finally:
        controller.abort()


def test_poll_step_times_out_and_aborts_with_message(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}

    tour = _make_tour("t7", [
        _make_step("never_resolves", lambda mw, ctx: None,
                   poll=True, timeout_message="gave up"),
    ])
    controller = TourController(main_window, tour)
    controller._SHORT_TIMEOUT_FOR_TESTS = 0.2
    controller.start()
    qtbot.waitUntil(lambda: OnboardingSettings().completed_tours.get("t7") is True, timeout=2000)
    assert not controller._coach_mark.isVisible()


def test_skip_sets_completed_and_hides_overlay(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}

    tour = _make_tour("t8", [_make_step("only", lambda mw, ctx: main_window.productTree)])
    controller = TourController(main_window, tour)
    controller.start()
    qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)

    controller._coach_mark.skip_requested.emit()

    assert not controller._coach_mark.isVisible()
    assert OnboardingSettings().completed_tours.get("t8") is True


def test_replaying_after_completion_does_not_double_fire_on_stale_connections(main_window, qtbot):
    """Regression guard: a finished/aborted controller must disconnect its
    per-step completion signal, or a second (replay) controller's own state
    gets corrupted by the first controller's dead handler still reacting to
    the shared, long-lived main_window's signals."""
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    tour = _make_tour("t9", [
        _make_step("first", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: main_window.panel_added),
        _make_step("second", lambda mw, ctx: main_window.productTree),
    ])

    first = TourController(main_window, tour)
    first.start()
    qtbot.waitUntil(lambda: first._coach_mark.isVisible(), timeout=1000)
    first.abort()
    assert first.is_finished is True

    second = TourController(main_window, tour)
    second.start()
    try:
        qtbot.waitUntil(lambda: second._coach_mark.isVisible(), timeout=1000)
        main_window.panel_added.emit(object())
        qtbot.waitUntil(lambda: second._current_step().step_id == "second", timeout=1000)
        assert second._step_index == 1
    finally:
        second.abort()


def test_finish_sets_is_finished_and_disposes_coach_mark_and_controller(main_window, qtbot):
    import shiboken6
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    tour = _make_tour("t10", [_make_step("only", lambda mw, ctx: main_window.productTree)])
    controller = TourController(main_window, tour)
    controller.start()
    qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)

    coach_mark = controller._coach_mark
    assert controller.is_finished is False

    controller.abort()

    assert controller.is_finished is True
    qtbot.waitUntil(lambda: not shiboken6.isValid(coach_mark), timeout=1000)
    qtbot.waitUntil(lambda: not shiboken6.isValid(controller), timeout=1000)


def test_deferred_cleanup_tolerates_coach_mark_and_controller_already_destroyed(
        main_window, qtbot, monkeypatch):
    import shiboken6
    from SciQLop.components.onboarding.ui import tour_controller as tc_mod
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    captured = {}

    def capture_single_shot(_delay, fn):
        captured["fn"] = fn

    monkeypatch.setattr(tc_mod.QTimer, "singleShot", capture_single_shot)

    tour = _make_tour("t11", [_make_step("only", lambda mw, ctx: main_window.productTree)])
    controller = TourController(main_window, tour)
    controller.start()
    qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)

    coach_mark = controller._coach_mark
    controller.abort()
    assert "fn" in captured

    coach_mark.deleteLater()
    controller.deleteLater()
    qtbot.waitUntil(lambda: not shiboken6.isValid(coach_mark), timeout=1000)
    qtbot.waitUntil(lambda: not shiboken6.isValid(controller), timeout=1000)

    captured["fn"]()  # must not raise RuntimeError: Internal C++ object already deleted


def test_target_destroyed_mid_step_aborts_tour_without_crash(qapp, sciqlop_resources, qtbot):
    """Uses a disposable, per-test main window (not the shared session-scoped
    `main_window` fixture) because this test destroys a widget that fixture
    is expected to keep alive for every other test in the suite."""
    from SciQLop.core.ui.mainwindow import SciQLopMainWindow
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}

    mw = SciQLopMainWindow()
    try:
        target = mw.productTree
        tour = _make_tour("t12", [_make_step("only", lambda mw_, ctx: target)])
        controller = TourController(mw, tour)
        controller.start()
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)

        target.deleteLater()
        qtbot.waitUntil(lambda: OnboardingSettings().completed_tours.get("t12") is True, timeout=2000)
        assert not controller._coach_mark.isVisible()
    finally:
        mw.close()


def test_real_getting_started_tour_advances_on_real_panel_creation(main_window, qtbot):
    """One true end-to-end smoke test against the real, registered
    Getting Started tour -- proves the ported content actually works
    through the generalized controller, not just fabricated test tours."""
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    registry.register_builtin_tours()
    tour = registry.get_tour("getting_started")
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: resolve_add_panel_button(main_window, {}) is not None, timeout=1000)
        resolve_add_panel_button(main_window, {}).click()
        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "open_products", timeout=2000)
        assert controller._context["create_panel"] is not None
    finally:
        controller.abort()
        for name in main_window.plot_panels():
            main_window.remove_panel(main_window.plot_panel(name))
```

### Step 23: Run the test to verify it fails

Run: `uv run pytest tests/test_onboarding_tour_controller.py -v --no-xvfb`
Expected: FAIL — `TypeError: TourController.__init__() missing 1 required positional argument: 'tour'` (old controller still takes only `main_window`).

### Step 24: Rewrite `ui/tour_controller.py`

```python
import shiboken6
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import get_tour
from SciQLop.components.onboarding.backend.settings import OnboardingSettings
from SciQLop.components.onboarding.ui.coach_mark import CoachMark
from SciQLop.components.sciqlop_logging import getLogger

log = getLogger(__name__)

_POLL_INTERVAL_S = 0.25


def _log_safely(message: str, level: str = "info") -> None:
    """Logging must never crash the app. The module-level logger's Qt
    signal can itself already be torn down if this fires from deep inside
    an interpreter/QApplication shutdown cascade -- swallow that one,
    narrow failure mode rather than let a diagnostic log call bring down
    shutdown."""
    try:
        getattr(log, level)(message)
    except RuntimeError:
        pass


def _normalize_completion(result):
    """A step's completion callable returns a bare Signal, a
    (Signal, predicate) tuple, or None. Normalize to (Signal, predicate)
    so the controller has one shape to connect."""
    if result is None:
        return None
    if isinstance(result, tuple):
        return result
    return result, (lambda *args: True)


def _store_completion_args(context: dict, step_id: str, args: tuple) -> None:
    if len(args) == 0:
        context[step_id] = True
    elif len(args) == 1:
        context[step_id] = args[0]
    else:
        context[step_id] = args


class TourController(QObject):
    """Walks a Tour's steps against a live SciQLopMainWindow, one CoachMark
    at a time, advancing on each step's completion signal or on the coach
    mark's own dismiss/skip actions. Carries no knowledge of which specific
    tour it's running -- every branch is driven by the step's own resolver/
    completion callables.

    Every step's completion connection is torn down as soon as that step is
    left (advance, abort, or replaced by a new step) -- main_window and its
    dock widgets/panels outlive any single tour run, so a stale connection
    left dangling past its step would keep firing into a finished
    controller on a later, unrelated replay.
    """

    _SHORT_TIMEOUT_FOR_TESTS: float | None = None

    def __init__(self, main_window, tour: Tour):
        super().__init__(main_window)
        self._main_window = main_window
        self._tour = tour
        self._coach_mark = CoachMark(main_window)
        self._coach_mark.skip_requested.connect(self._on_skip)
        self._coach_mark.dismiss_clicked.connect(self._on_dismiss)
        self._coach_mark.target_destroyed.connect(self._on_target_gone)
        self._step_index = 0
        self._poll_timer: QTimer | None = None
        self._poll_deadline_s = 0.0
        self._context: dict = {}
        self._active_signal = None
        self._active_slot = None
        self._finished = False

    @property
    def is_finished(self) -> bool:
        return self._finished

    def _current_step(self) -> TourStep:
        return self._tour.steps[self._step_index]

    def start(self) -> None:
        self._step_index = 0
        self._enter_current_step()

    def abort(self, message: str | None = None) -> None:
        self._stop_polling()
        self._disconnect_active_completion()
        self._finish()
        if message:
            _log_safely(message)

    def _finish(self) -> None:
        """Mark the tour as over and detach the controller from CoachMark's
        own signals. Idempotent: safe to call from multiple exit paths."""
        if self._finished:
            return
        self._finished = True
        self._detach_coach_mark_signals()
        self._coach_mark.hide()
        with OnboardingSettings() as s:
            s.completed_tours[self._tour.id] = True
        self._dispose()

    def _dispose(self) -> None:
        coach_mark = self._coach_mark

        def _cleanup():
            if shiboken6.isValid(coach_mark):
                coach_mark.dispose()
                coach_mark.deleteLater()
            if shiboken6.isValid(self):
                self.deleteLater()

        QTimer.singleShot(0, _cleanup)

    def _detach_coach_mark_signals(self) -> None:
        for signal, slot in (
                (self._coach_mark.skip_requested, self._on_skip),
                (self._coach_mark.dismiss_clicked, self._on_dismiss),
                (self._coach_mark.target_destroyed, self._on_target_gone)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _effective_timeout(self, step: TourStep) -> float | None:
        if self._SHORT_TIMEOUT_FOR_TESTS is not None:
            return self._SHORT_TIMEOUT_FOR_TESTS
        return step.timeout_s

    def _resolve_target(self, step: TourStep):
        return step.resolver(self._main_window, self._context)

    def _enter_current_step(self) -> None:
        step = self._current_step()
        target = self._resolve_target(step)

        if target is None and not step.poll:
            QApplication.processEvents()
            target = self._resolve_target(step)

        if step.poll and target is None:
            self._start_polling(step)
            return

        if target is None:
            _log_safely(f"Onboarding step {step.step_id!r}: target not found, aborting tour",
                        level="warning")
            self.abort()
            return

        self._show_step(step, target)

    def _start_polling(self, step: TourStep) -> None:
        import time
        self._poll_deadline_s = time.monotonic() + (self._effective_timeout(step) or 0.0)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(int(_POLL_INTERVAL_S * 1000))
        self._poll_timer.timeout.connect(lambda: self._poll_step(step))
        self._poll_timer.start()

    def _poll_step(self, step: TourStep) -> None:
        import time
        target = self._resolve_target(step)
        if target is not None:
            self._stop_polling()
            self._show_step(step, target)
            return
        if time.monotonic() >= self._poll_deadline_s:
            self._stop_polling()
            self.abort(step.timeout_message)

    def _stop_polling(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None

    def _disconnect_active_completion(self) -> None:
        if self._active_signal is not None and self._active_slot is not None:
            try:
                self._active_signal.disconnect(self._active_slot)
            except (RuntimeError, TypeError):
                pass
        self._active_signal = None
        self._active_slot = None

    def _show_step(self, step: TourStep, target) -> None:
        if isinstance(target, tuple):
            widget, local_rect = target
        else:
            widget, local_rect = target, None

        show_dismiss = step.completion is None
        self._coach_mark.show_for(widget, step.title, step.body,
                                  rect=local_rect, show_dismiss=show_dismiss)

        self._disconnect_active_completion()
        raw = step.completion(self._main_window, self._context) if step.completion else None
        normalized = _normalize_completion(raw)
        if normalized is not None:
            signal, predicate = normalized
            self._active_signal = signal

            def _slot(*args, _step=step, _predicate=predicate):
                if _predicate(*args):
                    _store_completion_args(self._context, _step.step_id, args)
                    self._advance()

            self._active_slot = _slot
            self._active_signal.connect(self._active_slot)
        else:
            self._active_signal = None
            self._active_slot = None

    def _on_dismiss(self) -> None:
        self._advance()

    def _on_skip(self) -> None:
        self.abort()

    def _on_target_gone(self) -> None:
        _log_safely("Onboarding tour target was destroyed mid-step; aborting")
        self.abort()

    def _advance(self) -> None:
        self._disconnect_active_completion()
        self._coach_mark.hide()
        self._step_index += 1
        if self._step_index >= len(self._tour.steps):
            self._finish()
            return
        self._enter_current_step()


def run_tour(main_window, tour_id: str) -> TourController | None:
    tour = get_tour(tour_id)
    if tour is None:
        _log_safely(f"Onboarding: unknown tour {tour_id!r}, not starting", level="warning")
        return None
    controller = TourController(main_window, tour)
    controller.start()
    return controller
```

### Step 25: Run the test to verify it passes

Run: `uv run pytest tests/test_onboarding_tour_controller.py -v --no-xvfb`
Expected: PASS (14 tests).

### Step 26: Update `backend/settings.py`

```python
from typing import ClassVar, Dict

from pydantic import Field

from SciQLop.components.settings.backend.entry import ConfigEntry, SettingsCategory


class OnboardingSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Onboarding"

    completed_tours: Dict[str, bool] = Field(default={})
```

This intentionally breaks `mainwindow.py` and `tests/test_onboarding_settings.py`,
`tests/test_onboarding_integration.py`, `tests/test_onboarding_wiring.py`
(they still reference `.tour_completed`) — Task 2 fixes every one of them.
Do not run the full suite between this step and the end of Task 2.

### Step 27: Update `__init__.py`

```python
from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import register_tour

__all__ = ["Tour", "TourStep", "register_tour"]
```

### Step 28: Commit

```bash
git add SciQLop/components/onboarding/ui/tour_controller.py \
        SciQLop/components/onboarding/backend/settings.py \
        SciQLop/components/onboarding/__init__.py \
        tests/test_onboarding_tour_controller.py
git commit -m "refactor(onboarding): generalize TourController to run any Tour"
```

---

## Task 2: Wire the new engine into `SciQLopMainWindow`

Consumes Task 1's `run_tour(main_window, tour_id)`, `register_builtin_tours()`,
`OnboardingSettings.completed_tours`. Fixes the breakage `settings.py`'s
Step 26 introduced. Produces the `_start_tour`/`_maybe_run_onboarding_tour`
methods later tasks (picker) call into.

**Files:**
- Modify: `SciQLop/core/ui/mainwindow.py`
- Test: `tests/test_onboarding_settings.py` (rewrite)
- Test: `tests/test_onboarding_wiring.py` (rewrite, minus picker-specific tests)
- Test: `tests/test_onboarding_integration.py` (rewrite)

**Interfaces:**
- Consumes: `run_tour(main_window, tour_id)`, `registry.register_builtin_tours()`, `OnboardingSettings.completed_tours` (Task 1).
- Produces: `SciQLopMainWindow._start_tour(tour_id: str) -> None`, `SciQLopMainWindow._maybe_run_onboarding_tour(*_args) -> None` (used by Task 4's picker).

### Step 1: Write the failing tests

Rewrite `tests/test_onboarding_settings.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "SciQLop.components.settings.backend.entry.SCIQLOP_CONFIG_DIR",
        str(tmp_path))


def test_completed_tours_defaults_to_empty():
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    assert OnboardingSettings().completed_tours == {}


def test_completed_tours_persists_across_instances():
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    with OnboardingSettings() as s:
        s.completed_tours = {"getting_started": True}
    assert OnboardingSettings().completed_tours == {"getting_started": True}
```

Rewrite `tests/test_onboarding_wiring.py`:

```python
from .fixtures import *
import pytest


def test_tools_menu_has_take_a_tour_action(main_window):
    actions = [a.text() for a in main_window.toolsMenu.actions()]
    assert "Take a Tour…" in actions


def test_maybe_run_onboarding_tour_skips_when_getting_started_completed(main_window, qtbot):
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {"getting_started": True}

    main_window._onboarding_controller = None
    main_window._maybe_run_onboarding_tour(None)
    qtbot.wait(200)
    assert main_window._onboarding_controller is None


def test_maybe_run_onboarding_tour_starts_when_not_completed(main_window, qtbot):
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}

    main_window._onboarding_controller = None
    main_window._maybe_run_onboarding_tour(None)
    qtbot.waitUntil(lambda: main_window._onboarding_controller is not None, timeout=1000)
    assert main_window._onboarding_controller._tour.id == "getting_started"
    main_window._onboarding_controller.abort()


def test_starting_tour_twice_in_a_row_does_not_stack_a_second_controller(main_window, qtbot):
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}

    main_window._onboarding_controller = None
    try:
        main_window._start_tour("getting_started")
        first_controller = main_window._onboarding_controller

        main_window._start_tour("getting_started")
        second_controller = main_window._onboarding_controller

        assert second_controller is first_controller
    finally:
        if main_window._onboarding_controller is not None:
            main_window._onboarding_controller.abort()


def test_start_tour_with_unknown_id_does_not_crash(main_window):
    main_window._onboarding_controller = None
    main_window._start_tour("no_such_tour")
    assert main_window._onboarding_controller is None
```

Rewrite `tests/test_onboarding_integration.py`:

```python
from .fixtures import *


def test_full_tour_completes_through_all_five_steps_or_aborts_cleanly(main_window, qtbot):
    """Drives steps 1-2 for real (deterministic, no network). Step 3 depends
    on a real product provider being registered -- in CI/offline test runs
    that's typically not the case, so this test accepts either a full
    completion (if a provider happens to be loaded) or the documented
    step-3 abort, and asserts both leave the app in a clean, consistent
    state either way."""
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    from SciQLop.components.onboarding.backend.targets import (
        resolve_add_panel_button, side_tab_resolver)
    from SciQLop.components.onboarding.ui.tour_controller import run_tour

    with OnboardingSettings() as s:
        s.completed_tours = {}

    controller = run_tour(main_window, "getting_started")
    controller._SHORT_TIMEOUT_FOR_TESTS = 1.0

    try:
        qtbot.waitUntil(
            lambda: resolve_add_panel_button(main_window, {}) is not None, timeout=1000)
        assert controller._current_step().step_id == "create_panel"
        resolve_add_panel_button(main_window, {}).click()

        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "open_products",
            timeout=2000)

        side_tab_resolver("Products")(main_window, {}).click()
        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "plot_product"
            or not controller._coach_mark.isVisible(),
            timeout=2000)

        qtbot.waitUntil(
            lambda: OnboardingSettings().completed_tours.get("getting_started") is True,
            timeout=3000)
        assert not controller._coach_mark.isVisible()
    finally:
        controller.abort()
        for name in main_window.plot_panels():
            main_window.remove_panel(main_window.plot_panel(name))
```

### Step 2: Run the tests to verify they fail

Run: `uv run pytest tests/test_onboarding_settings.py tests/test_onboarding_wiring.py tests/test_onboarding_integration.py -v --no-xvfb`
Expected: FAIL — `AttributeError: 'OnboardingSettings' object has no attribute 'tour_completed'` no longer applies (Step 26 already changed it), but `main_window._start_tour` doesn't exist yet, `main_window.toolsMenu` still has the old "Replay Onboarding Tour" text, `run_tour` now requires a `tour_id` argument mainwindow.py doesn't pass yet.

### Step 3: Update `SciQLop/core/ui/mainwindow.py`

Find and replace the Tools-menu block (currently around line 171-176):

```python
        replay_tour = self.toolsMenu.addAction(
            "Replay Onboarding Tour", self._replay_onboarding_tour)
        replay_tour.setToolTip(rich_tooltip(
            "Replay Onboarding Tour",
            "Walk through creating a plot panel, finding the Products "
            "browser, and plotting your first product."))
```

with:

```python
        take_a_tour = self.toolsMenu.addAction(
            "Take a Tour…", self._open_tour_picker)
        take_a_tour.setToolTip(rich_tooltip(
            "Take a Tour",
            "Pick a guided walkthrough of a SciQLop feature."))
```

Find and replace the quickstart shortcut registration (currently around line 246-248):

```python
        sciqlop_app().add_quickstart_shortcut(
            name="Take the tour", description="Learn how to create your first plot",
            icon=theme_icon("assistant"), callback=self._start_onboarding_tour)
```

with:

```python
        sciqlop_app().add_quickstart_shortcut(
            name="Take a Tour", description="Pick a guided walkthrough of a SciQLop feature",
            icon=theme_icon("assistant"), callback=self._open_tour_picker)
```

Find, in `_setup_side_panels`, the line `self._onboarding_controller = None` (currently
around line 195) and add a call to `register_builtin_tours()` immediately before it:

```python
        from SciQLop.components.onboarding.backend.registry import register_builtin_tours
        register_builtin_tours()
        self._onboarding_controller = None
        wm.workspace_loaded.connect(self._maybe_run_onboarding_tour)
```

Find and replace the three onboarding methods (currently around line 616-628):

```python
    def _maybe_run_onboarding_tour(self, *_args) -> None:
        if OnboardingSettings().tour_completed:
            return
        QtCore.QTimer.singleShot(500, self._start_onboarding_tour)

    def _replay_onboarding_tour(self) -> None:
        self._start_onboarding_tour()

    def _start_onboarding_tour(self) -> None:
        controller = self._onboarding_controller
        if controller is not None and shiboken6.isValid(controller) and not controller.is_finished:
            return
        self._onboarding_controller = run_tour(self)
```

with:

```python
    def _maybe_run_onboarding_tour(self, *_args) -> None:
        if OnboardingSettings().completed_tours.get("getting_started", False):
            return
        QtCore.QTimer.singleShot(500, lambda: self._start_tour("getting_started"))

    def _open_tour_picker(self) -> None:
        from SciQLop.components.onboarding.ui.tour_picker import TourPicker
        self._tour_picker = TourPicker(self)
        self._tour_picker.show()

    def _start_tour(self, tour_id: str) -> None:
        controller = self._onboarding_controller
        if controller is not None and shiboken6.isValid(controller) and not controller.is_finished:
            return
        self._onboarding_controller = run_tour(self, tour_id)
```

Note: `_open_tour_picker` imports `TourPicker`, which does not exist until
Task 4. Until Task 4 lands, `_open_tour_picker` will raise `ImportError` if
actually called — it is wired into the menu/quickstart in this task but not
exercised by any test in this task (the new `test_onboarding_wiring.py`
above deliberately does not test the Tools-menu action's *behavior*, only
its label, and does not test the quickstart shortcut's behavior either —
those come back in Task 4 once `TourPicker` exists). This is the one
deliberate exception to "every task leaves tests green": the action exists
and is labeled correctly, but clicking it doesn't work until Task 4. Flag
this explicitly in Task 2's review.

### Step 4: Run the tests to verify they pass

Run: `uv run pytest tests/test_onboarding_settings.py tests/test_onboarding_wiring.py tests/test_onboarding_integration.py -v --no-xvfb`
Expected: PASS (all tests in all three files).

### Step 5: Commit

```bash
git add SciQLop/core/ui/mainwindow.py \
        tests/test_onboarding_settings.py \
        tests/test_onboarding_wiring.py \
        tests/test_onboarding_integration.py
git commit -m "refactor(onboarding): wire mainwindow to the multi-tour engine"
```

---

## Task 3: New built-in tours — Catalogs and Settings

Independently reviewable: adds new tours and their resolvers, does not
change the engine or Getting Started's behavior. The two steps identified
during design as depending on optional prior user action ("Add Event",
"overlay on a panel") use `poll=True` + a short timeout, exactly like
Getting Started's step 3 — same established mechanism, not new controller
behavior.

**Files:**
- Modify: `SciQLop/components/onboarding/backend/targets.py`
- Modify: `SciQLop/components/onboarding/backend/registry.py` (extend `register_builtin_tours`)
- Create: `SciQLop/components/onboarding/backend/tour_catalogs.py`
- Create: `SciQLop/components/onboarding/backend/tour_settings.py`
- Test: `tests/test_onboarding_targets.py` (extend)
- Test: `tests/test_onboarding_tour_catalogs.py` (new)
- Test: `tests/test_onboarding_tour_settings.py` (new)

**Interfaces:**
- Consumes: `side_tab_resolver`, `completions.dock_visible`, `completions.plot_added_to` (Task 1); `register_tour` (Task 1).
- Produces: `CATALOGS: Tour`, `SETTINGS: Tour` (importable, registered as a side effect of `register_builtin_tours()`).

### Step 1: Write the failing tests for the new resolvers

Append to `tests/test_onboarding_targets.py`:

```python
def test_resolve_catalog_tree_finds_a_tree_view(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_catalog_tree
    from PySide6.QtWidgets import QTreeView
    result = resolve_catalog_tree(main_window, {})
    assert isinstance(result, QTreeView)


def test_resolve_add_event_button_matches_visibility_state(main_window):
    """Doesn't assert a specific None/not-None outcome: main_window is a
    session-scoped fixture shared with unrelated test files, so whether a
    catalog happens to be selected elsewhere in the session isn't this
    test's business. What must always hold is the function's own contract:
    it never returns a hidden button."""
    from SciQLop.components.onboarding.backend.targets import resolve_add_event_button
    result = resolve_add_event_button(main_window, {})
    if result is not None:
        assert result.isVisible()


def test_resolve_any_plot_with_data_returns_none_when_no_plots():
    from SciQLop.components.onboarding.backend.targets import resolve_any_plot_with_data
    from unittest.mock import MagicMock

    fake_main_window = MagicMock()
    fake_main_window.plot_panels.return_value = []
    assert resolve_any_plot_with_data(fake_main_window, {}) is None


def test_resolve_any_plot_with_data_returns_last_plot_of_a_panel_with_plots():
    from SciQLop.components.onboarding.backend.targets import resolve_any_plot_with_data
    from unittest.mock import MagicMock

    fake_widget = object()
    fake_panel = MagicMock()
    fake_panel.plots.return_value = [fake_widget]
    fake_main_window = MagicMock()
    fake_main_window.plot_panels.return_value = ["panel1"]
    fake_main_window.plot_panel.return_value = fake_panel
    assert resolve_any_plot_with_data(fake_main_window, {}) is fake_widget


def test_resolve_settings_category_list_finds_a_list_view(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_settings_category_list
    from PySide6.QtWidgets import QListView
    result = resolve_settings_category_list(main_window, {})
    assert isinstance(result, QListView)
```

### Step 2: Run the tests to verify they fail

Run: `uv run pytest tests/test_onboarding_targets.py -v --no-xvfb`
Expected: FAIL — `ImportError` (the four new resolvers don't exist yet).

### Step 3: Add the new resolvers to `backend/targets.py`

Append to the end of `SciQLop/components/onboarding/backend/targets.py` (add
`QPushButton, QListView` to the existing `PySide6.QtWidgets` import line at
the top of the file):

```python
def resolve_catalog_tree(main_window, context) -> QTreeView | None:
    trees = main_window.catalogs_browser.findChildren(QTreeView)
    return trees[0] if trees else None


def resolve_add_event_button(main_window, context) -> QWidget | None:
    for button in main_window.catalogs_browser.findChildren(QPushButton):
        if button.text() == "Add Event" and button.isVisible():
            return button
    return None


def resolve_any_plot_with_data(main_window, context) -> QWidget | None:
    for name in main_window.plot_panels():
        panel = main_window.plot_panel(name)
        if panel is None:
            continue
        plots = panel.plots()
        if plots:
            return plots[-1]
    return None


def resolve_settings_category_list(main_window, context) -> QListView | None:
    views = main_window.settings_panel.findChildren(QListView)
    return views[0] if views else None
```

Update the top-of-file import line from:

```python
from PySide6.QtWidgets import QTreeView, QWidget
```

to:

```python
from PySide6.QtWidgets import QTreeView, QWidget, QPushButton, QListView
```

### Step 4: Run the tests to verify they pass

Run: `uv run pytest tests/test_onboarding_targets.py -v --no-xvfb`
Expected: PASS (all tests).

### Step 5: Commit

```bash
git add SciQLop/components/onboarding/backend/targets.py \
        tests/test_onboarding_targets.py
git commit -m "feat(onboarding): add Catalogs and Settings target resolvers"
```

### Step 6: Write the failing tests for the two new tours

Create `tests/test_onboarding_tour_catalogs.py`:

```python
def test_catalogs_has_four_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS
    assert [s.step_id for s in CATALOGS.steps] == [
        "open_catalogs", "create_catalog", "add_event", "overlay_catalog",
    ]


def test_add_event_and_overlay_steps_poll_with_timeout():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS
    by_id = {s.step_id: s for s in CATALOGS.steps}
    for step_id in ("add_event", "overlay_catalog"):
        assert by_id[step_id].poll is True
        assert by_id[step_id].timeout_s is not None
        assert by_id[step_id].timeout_message is not None
    for step_id in ("open_catalogs", "create_catalog"):
        assert by_id[step_id].poll is False


def test_only_open_catalogs_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS
    by_id = {s.step_id: s for s in CATALOGS.steps}
    assert by_id["open_catalogs"].completion is not None
    for step_id in ("create_catalog", "add_event", "overlay_catalog"):
        assert by_id[step_id].completion is None


def test_catalogs_is_registered():
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS
    registry.register_builtin_tours()
    assert registry.get_tour("catalogs") is CATALOGS
```

Create `tests/test_onboarding_tour_settings.py`:

```python
def test_settings_has_two_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS
    assert [s.step_id for s in SETTINGS.steps] == ["open_settings", "browse_categories"]


def test_only_open_settings_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS
    by_id = {s.step_id: s for s in SETTINGS.steps}
    assert by_id["open_settings"].completion is not None
    assert by_id["browse_categories"].completion is None


def test_settings_is_registered():
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS
    registry.register_builtin_tours()
    assert registry.get_tour("settings") is SETTINGS
```

### Step 7: Run the tests to verify they fail

Run: `uv run pytest tests/test_onboarding_tour_catalogs.py tests/test_onboarding_tour_settings.py -v --no-xvfb`
Expected: FAIL — `ModuleNotFoundError` for both new modules.

### Step 8: Create `backend/tour_catalogs.py`

```python
from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import register_tour
from SciQLop.components.onboarding.backend import targets, completions

_NO_CATALOG_MESSAGE = (
    "Create or select a catalog to see event controls — replay this tour "
    "anytime from Tools → Take a Tour."
)
_NO_PANEL_MESSAGE = (
    "Plot something first to see how overlaying catalogs works — replay "
    "this tour anytime from Tools → Take a Tour."
)

CATALOGS = Tour(
    id="catalogs",
    title="Catalogs",
    description="Create catalogs, label events, and overlay them on plots.",
    steps=[
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
    ],
)

register_tour(CATALOGS)
```

### Step 9: Create `backend/tour_settings.py`

```python
from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import register_tour
from SciQLop.components.onboarding.backend import targets, completions

SETTINGS = Tour(
    id="settings",
    title="Settings",
    description="Find where SciQLop's appearance, plugins, and workspace options live.",
    steps=[
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
    ],
)

register_tour(SETTINGS)
```

### Step 10: Extend `register_builtin_tours` in `backend/registry.py`

Replace:

```python
def register_builtin_tours() -> None:
    """Import every built-in tour module -- each registers itself as a
    module-level side effect. Safe to call more than once: Python only
    executes a module body on its first import."""
    from SciQLop.components.onboarding.backend import tour_getting_started  # noqa: F401
```

with:

```python
def register_builtin_tours() -> None:
    """Import every built-in tour module -- each registers itself as a
    module-level side effect. Safe to call more than once: Python only
    executes a module body on its first import."""
    from SciQLop.components.onboarding.backend import (  # noqa: F401
        tour_getting_started, tour_catalogs, tour_settings,
    )
```

### Step 11: Run the tests to verify they pass

Run: `uv run pytest tests/test_onboarding_tour_catalogs.py tests/test_onboarding_tour_settings.py -v --no-xvfb`
Expected: PASS (4 tests + 3 tests).

### Step 12: Commit

```bash
git add SciQLop/components/onboarding/backend/tour_catalogs.py \
        SciQLop/components/onboarding/backend/tour_settings.py \
        SciQLop/components/onboarding/backend/registry.py \
        tests/test_onboarding_tour_catalogs.py \
        tests/test_onboarding_tour_settings.py
git commit -m "feat(onboarding): add Catalogs and Settings built-in tours"
```

---

## Task 4: Tour picker dialog

Depends on Task 2 (`main_window._start_tour`) and Task 3 (more than one
tour worth picking between). Makes the `_open_tour_picker` call added in
Task 2 actually work — this is the task that finally makes `TourPicker`
importable, closing out Task 2's one deliberate gap.

**Files:**
- Create: `SciQLop/components/onboarding/ui/tour_picker.py`
- Test: `tests/test_onboarding_tour_picker.py` (new)
- Test: `tests/test_onboarding_wiring.py` (extend)

**Interfaces:**
- Consumes: `registry.all_tours()`, `OnboardingSettings.completed_tours` (Task 1); `main_window._start_tour(tour_id)` (Task 2).
- Produces: `TourPicker(main_window)` — a `QDialog` with `_items_by_tour_id: dict[str, QListWidgetItem]` and `_start_selected()`, used only by `mainwindow.py`'s `_open_tour_picker`.

### Step 1: Write the failing tests

Create `tests/test_onboarding_tour_picker.py`:

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
        assert {"getting_started", "catalogs", "settings"} <= registered_ids
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
        assert "Completed" not in picker._items_by_tour_id["catalogs"].text()
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
    picker._list.setCurrentItem(picker._items_by_tour_id["settings"])
    picker._start_selected()

    try:
        qtbot.waitUntil(
            lambda: main_window._onboarding_controller is not None
            and main_window._onboarding_controller._tour.id == "settings",
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

Append to `tests/test_onboarding_wiring.py`:

```python
def test_take_a_tour_action_opens_the_picker(main_window):
    action = next(a for a in main_window.toolsMenu.actions() if a.text() == "Take a Tour…")
    action.trigger()
    assert main_window._tour_picker.isVisible()
    main_window._tour_picker.close()


def test_take_a_tour_quickstart_shortcut_registered(main_window, qapp):
    assert "Take a Tour" in qapp.quickstart_shortcuts


def test_take_a_tour_shortcut_opens_the_picker(main_window, qapp):
    shortcut = qapp.quickstart_shortcut("Take a Tour")
    shortcut["callback"]()
    assert main_window._tour_picker.isVisible()
    main_window._tour_picker.close()
```

### Step 2: Run the tests to verify they fail

Run: `uv run pytest tests/test_onboarding_tour_picker.py tests/test_onboarding_wiring.py -v --no-xvfb`
Expected: FAIL — `ModuleNotFoundError: No module named '...ui.tour_picker'`.

### Step 3: Create `ui/tour_picker.py`

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton

from SciQLop.components.onboarding.backend.registry import all_tours
from SciQLop.components.onboarding.backend.settings import OnboardingSettings


class TourPicker(QDialog):
    """Lists every registered tour (built-in and plugin-contributed) and
    starts whichever one the user picks. Non-modal by design: it must not
    block the app's event loop, and its "Start" action just hands off to
    main_window._start_tour and closes."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.setWindowTitle("Take a Tour")
        self._main_window = main_window
        self._items_by_tour_id: dict[str, QListWidgetItem] = {}

        layout = QVBoxLayout(self)
        self._list = QListWidget(self)
        layout.addWidget(self._list)
        self._list.itemDoubleClicked.connect(lambda _item: self._start_selected())

        start_button = QPushButton("Start", self)
        start_button.clicked.connect(self._start_selected)
        layout.addWidget(start_button)

        self._populate()

    def _populate(self) -> None:
        completed = OnboardingSettings().completed_tours
        for tour in all_tours():
            suffix = " (Completed)" if completed.get(tour.id, False) else ""
            item = QListWidgetItem(f"{tour.title}{suffix} — {tour.description}")
            item.setData(Qt.ItemDataRole.UserRole, tour.id)
            self._list.addItem(item)
            self._items_by_tour_id[tour.id] = item

    def _start_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        tour_id = item.data(Qt.ItemDataRole.UserRole)
        self.close()
        self._main_window._start_tour(tour_id)
```

### Step 4: Run the tests to verify they pass

Run: `uv run pytest tests/test_onboarding_tour_picker.py tests/test_onboarding_wiring.py -v --no-xvfb`
Expected: PASS (4 tests + 3 new tests, all prior `test_onboarding_wiring.py` tests still passing).

### Step 5: Commit

```bash
git add SciQLop/components/onboarding/ui/tour_picker.py \
        tests/test_onboarding_tour_picker.py \
        tests/test_onboarding_wiring.py
git commit -m "feat(onboarding): add the Take a Tour picker dialog"
```

---

## Task 5: Plugin-registration round-trip test

Proves the stated purpose of this whole refactor: a plugin can add a tour
through the public API alone, with no core code change. Small and
standalone — depends only on Task 1's `__init__.py` exports and Task 4's
working `run_tour`/`TourController` (to prove the fake tour is not just
listed but actually runnable).

**Files:**
- Test: `tests/test_onboarding_plugin_api.py` (new)

**Interfaces:**
- Consumes: `SciQLop.components.onboarding.{Tour, TourStep, register_tour}` (Task 1, the public plugin-facing surface).

### Step 1: Write the failing test

Create `tests/test_onboarding_plugin_api.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _forget_fake_plugin_tour():
    yield
    from SciQLop.components.onboarding.backend import registry
    registry._forget_tour_for_tests("fake_plugin_tour")


def test_a_plugin_can_register_a_tour_through_the_public_api(main_window, qtbot):
    """Simulates exactly what an out-of-tree plugin's load(main_window)
    would do: import only the public onboarding surface, build a Tour with
    its own resolver, and register it. No SciQLop core file changes for
    this to work is the entire point of this test."""
    from SciQLop.components.onboarding import Tour, TourStep, register_tour
    from SciQLop.components.onboarding.backend.registry import get_tour, all_tours
    from SciQLop.components.onboarding.ui.tour_controller import run_tour

    def _fake_plugin_widget_resolver(mw, context):
        return mw.productTree

    register_tour(Tour(
        id="fake_plugin_tour",
        title="Fake Plugin Tour",
        description="A tour a fake out-of-tree plugin registered.",
        steps=[TourStep(
            step_id="only_step", title="Fake step", body="Fake body.",
            resolver=_fake_plugin_widget_resolver,
        )],
    ))

    assert get_tour("fake_plugin_tour") is not None
    assert "fake_plugin_tour" in {t.id for t in all_tours()}

    controller = run_tour(main_window, "fake_plugin_tour")
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        assert controller._current_step().step_id == "only_step"
    finally:
        controller.abort()
```

### Step 2: Run the test to verify it fails

Run: `uv run pytest tests/test_onboarding_plugin_api.py -v --no-xvfb`
Expected: FAIL only if `__init__.py`'s exports are missing (they were
added in Task 1 Step 27) — if Tasks 1-4 are already done in order, this
test should actually PASS immediately. Run it anyway to confirm: this is
the test that proves the whole plan's stated goal, so it must be seen
passing explicitly, not assumed.

### Step 3: If it fails, fix `__init__.py`

Only if Step 2 failed: re-check `SciQLop/components/onboarding/__init__.py`
matches Task 1 Step 27 exactly (`Tour`, `TourStep`, `register_tour` all
exported). No other code should need changes for this test to pass — if
something else is broken, that's a regression from an earlier task, not
new work for this task.

### Step 4: Run the test to verify it passes

Run: `uv run pytest tests/test_onboarding_plugin_api.py -v --no-xvfb`
Expected: PASS (1 test).

### Step 5: Commit

```bash
git add tests/test_onboarding_plugin_api.py
git commit -m "test(onboarding): prove the plugin tour-registration API works end to end"
```

---

## Task 6: Full onboarding suite verification

Final task: no new code, just proof the whole plan's worth of changes hang
together. Matches the precedent set by every prior onboarding session this
project has done (original build, both post-ship fixes) — the last step is
always a full run of every onboarding test file together, not just each
one individually.

**Files:** none (verification only).

### Step 1: Run the complete onboarding suite

Run:

```bash
uv run pytest tests/test_onboarding_registry.py tests/test_onboarding_completions.py \
  tests/test_onboarding_targets.py tests/test_onboarding_tour_getting_started.py \
  tests/test_onboarding_tour_catalogs.py tests/test_onboarding_tour_settings.py \
  tests/test_onboarding_tour_controller.py tests/test_onboarding_tour_picker.py \
  tests/test_onboarding_settings.py tests/test_onboarding_wiring.py \
  tests/test_onboarding_integration.py tests/test_onboarding_coach_mark.py \
  tests/test_onboarding_plugin_api.py --no-xvfb -v
```

Expected: every test PASSES (exit code 0). Read the actual pass count from
the output — do not infer success from a partial grep.

### Step 2: If anything fails, return to the task that owns the failing file

Do not patch the failure in this task. Identify which earlier task's
deliverable the failing test file belongs to, fix it there, and re-run
this task's full command from Step 1 again.

### Step 3: Confirm no stray references to the old API remain

```bash
grep -rn "tour_completed\|TOUR_STEPS\|RESOLVERS\b\|resolve_products_side_tab\|_replay_onboarding_tour\|_start_onboarding_tour\b" SciQLop/ tests/
```

Expected: no matches. (`resolve_products_side_tab` was replaced by
`side_tab_resolver("Products")`; `_start_onboarding_tour`/
`_replay_onboarding_tour` were replaced by `_start_tour`/
`_open_tour_picker`.) If anything matches, it's dead code or a missed
rename — fix it in the task that owns that file, not here.

### Step 4: Commit (only if Step 3 found and fixed something)

```bash
git add -u
git commit -m "chore(onboarding): remove stray references to the pre-refactor API"
```

If Step 3 found nothing, there is nothing to commit — the plan is complete.
