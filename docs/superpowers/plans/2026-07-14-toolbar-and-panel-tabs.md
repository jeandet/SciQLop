# Toolbar Relocation and Panel-Area "+" Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reclaim the top toolbar's screen space by hiding it by default (togglable from the View menu, zero plugin-API breakage) and let users grow a plot layout by clicking a "+" button on any dock area that already holds plot panels.

**Architecture:** Two independent, sequential changes to `SciQLopMainWindow`
(`SciQLop/core/ui/mainwindow.py`). (1) The existing `self.toolBar` keeps its
identity/position, just starts hidden with a native `QToolBar.toggleViewAction()`
wired into the View menu. (2) A new signal handler listens to QtAds's
`CDockManager.dockAreaCreated` and, for any area that turns out to hold at
least one plot panel, inserts a `QToolButton` into that area's title bar
(`CDockAreaTitleBar.insertWidget`) right after its tab strip; clicking it
docks a new plot panel as another tab in that same area.

**Tech Stack:** PySide6, PySide6QtAds (Qt Advanced Docking System), pytest-qt.

**Reference spec:** `docs/superpowers/specs/2026-07-14-toolbar-and-panel-tabs-design.md`

## Global Constraints

- `main_window.toolBar` must stay a real, always-present `QToolBar` object
  addressable via `.addAction()`/`.addWidget()` — this is a documented
  external plugin API (sismo, radio, cdf_workbench, msa plugins in the
  separate `plugins_sciqlop` repo). Do not rename, remove, or change its
  type. Do not touch anything in `plugins_sciqlop` — out of scope.
- Toolbar starts hidden (`setVisible(False)`) and is revealed only via the
  View menu's native `toggleViewAction()` — no custom show/hide code.
- The "+" button reuses the existing `theme_icon("add_graph")` — do not
  register a new icon.
- Clicking "+" must dock the new panel as **another tab in the same dock
  area** the button lives on, not a split.
- Run tests with `uv run pytest <path> -v` and read the actual pass/fail
  count before calling a task done.
- `main_window` in tests is a **session-scoped, shared** fixture
  (`tests/fixtures.py:22-44`) — every test that creates a panel/dock widget
  must clean it up (`main_window.remove_panel(...)`, or the
  `dw.closeDockWidget(); container.deleteLater(); release_name(...)` pattern
  used by `remove_native_plot_panel`) in a `finally` block, so state doesn't
  leak into later tests.

---

### Task 1: Toolbar hidden by default, toggle in View menu

**Files:**
- Modify: `SciQLop/core/ui/mainwindow.py:215-231` (`_setup_toolbar`)
- Test: `tests/test_mainwindow_toolbar.py` (create)

**Interfaces:**
- Consumes: `self.viewMenu` (already built by `_setup_menus`, called before
  `_setup_toolbar` in `_setup_ui`, `mainwindow.py:88-99`); `self.toolBar`
  (existing `QToolBar`, unchanged type/position).
- Produces: nothing new consumed by later tasks — Task 1 is independent of
  Task 2/3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mainwindow_toolbar.py`:

```python
from .fixtures import *


def test_toolbar_hidden_by_default(main_window):
    assert main_window.toolBar.isVisible() is False


def test_view_menu_exposes_toolbar_toggle(main_window):
    assert main_window.toolBar.toggleViewAction() in main_window.viewMenu.actions()


def test_toolbar_toggle_action_shows_and_hides_toolbar(main_window, qtbot):
    toggle = main_window.toolBar.toggleViewAction()
    try:
        toggle.trigger()
        qtbot.waitUntil(lambda: main_window.toolBar.isVisible(), timeout=1000)
    finally:
        if main_window.toolBar.isVisible():
            toggle.trigger()
        qtbot.waitUntil(lambda: not main_window.toolBar.isVisible(), timeout=1000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mainwindow_toolbar.py -v`
Expected: `test_toolbar_hidden_by_default` FAILs (`toolBar.isVisible()` is
`True` today); the other two may pass already since `toggleViewAction()` is
native `QToolBar` behavior — that's fine, Step 4 must not break them.

- [ ] **Step 3: Implement**

In `SciQLop/core/ui/mainwindow.py`, change `_setup_toolbar`
(`mainwindow.py:215-231`) from:

```python
    def _setup_toolbar(self):
        self.setWindowTitle("SciQLop")
        self.setWindowIcon(QtGui.QIcon("://icons/SciQLop.png"))
        self.toolBar = QtWidgets.QToolBar(self)
        self.toolBar.setWindowTitle("Toolbar")
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.toolBar)

        self.addTSPanel = QtGui.QAction(self)
```

to:

```python
    def _setup_toolbar(self):
        self.setWindowTitle("SciQLop")
        self.setWindowIcon(QtGui.QIcon("://icons/SciQLop.png"))
        self.toolBar = QtWidgets.QToolBar(self)
        self.toolBar.setWindowTitle("Toolbar")
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.toolBar)
        self.toolBar.setVisible(False)
        self.viewMenu.addAction(self.toolBar.toggleViewAction())

        self.addTSPanel = QtGui.QAction(self)
```

(Everything below `self.addTSPanel = QtGui.QAction(self)` in that method is
unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mainwindow_toolbar.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/core/ui/mainwindow.py tests/test_mainwindow_toolbar.py
git commit -m "feat(mainwindow): hide toolbar by default, toggle from View menu"
```

---

### Task 2: `new_native_plot_panel` accepts an explicit target dock area

**Files:**
- Modify: `SciQLop/core/ui/mainwindow.py:445-458` (`new_native_plot_panel`)
- Test: `tests/test_panel_area_add_button.py` (create — Task 3 extends this
  same file)

**Interfaces:**
- Consumes: `self.addWidgetIntoDock(allowed_area, widget, area=None, ...)`
  (existing, `mainwindow.py:411-438`, already accepts an `area` kwarg that
  is passed straight to `dock_manager.addDockWidgetTabToArea` when truthy).
- Produces: `new_native_plot_panel(self, name: Optional[str] = None, area: Optional[QtAds.CDockAreaWidget] = None) -> TimeSyncPanel`
  — Task 3's button click handler calls this with `area=<the button's area>`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_panel_area_add_button.py`:

```python
from .fixtures import *
import PySide6QtAds as QtAds


def _area_for(main_window, panel):
    dw = main_window.dock_manager.findDockWidget(panel.name)
    return dw.dockAreaWidget()


def test_new_native_plot_panel_docks_into_explicit_area(main_window, qtbot):
    panel1 = main_window.new_plot_panel()
    try:
        area = _area_for(main_window, panel1)
        before = area.dockWidgetsCount()

        panel2 = main_window.new_native_plot_panel(area=area)
        try:
            qtbot.waitUntil(lambda: area.dockWidgetsCount() == before + 1, timeout=1000)
            assert _area_for(main_window, panel2) is area
        finally:
            main_window.remove_panel(panel2)
    finally:
        main_window.remove_panel(panel1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_panel_area_add_button.py -v`
Expected: FAIL with `TypeError: new_native_plot_panel() got an unexpected
keyword argument 'area'`.

- [ ] **Step 3: Implement**

In `SciQLop/core/ui/mainwindow.py`, change `new_native_plot_panel`
(`mainwindow.py:445-449`) from:

```python
    def new_native_plot_panel(self, name: Optional[str] = None) -> TimeSyncPanel:
        panel = TimeSyncPanel(parent=None, name=auto_name(base="Panel", name=name),
                              time_range=self._default_time_range)
        container = PanelContainer(panel)
        self.addWidgetIntoDock(QtAds.DockWidgetArea.TopDockWidgetArea, container, delete_on_close=True)
```

to:

```python
    def new_native_plot_panel(self, name: Optional[str] = None,
                              area: Optional[QtAds.CDockAreaWidget] = None) -> TimeSyncPanel:
        panel = TimeSyncPanel(parent=None, name=auto_name(base="Panel", name=name),
                              time_range=self._default_time_range)
        container = PanelContainer(panel)
        self.addWidgetIntoDock(QtAds.DockWidgetArea.TopDockWidgetArea, container,
                               area=area, delete_on_close=True)
```

(The rest of the method — `panel.delete_me.connect(...)` through the
`return panel` — is unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_panel_area_add_button.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/core/ui/mainwindow.py tests/test_panel_area_add_button.py
git commit -m "feat(mainwindow): let new_native_plot_panel target an explicit dock area"
```

---

### Task 3: "+" button on every dock area holding plot panels

**Files:**
- Modify: `SciQLop/core/ui/mainwindow.py:121-136` (`_setup_dock_manager` —
  add one signal connection at the end)
- Modify: `SciQLop/core/ui/mainwindow.py` — add two new methods
  (`_on_dock_area_created`, `_ensure_add_panel_button`) immediately after
  `_drop_dead_panel_dock` (which currently ends at line 469)
- Test: `tests/test_panel_area_add_button.py` (extend — created in Task 2)

**Interfaces:**
- Consumes: `_extract_panel(dock_widget)` (module-level helper,
  `mainwindow.py:39-48`, already used elsewhere in this file — returns the
  `TimeSyncPanel`/`SciQLopMultiPlotPanel` behind a dock widget, or `None`);
  `new_native_plot_panel(self, name=None, area=None)` from Task 2;
  `QtAds.CDockManager.dockAreaCreated` signal (`Signal(CDockAreaWidget)`,
  fires whenever ADS constructs a new dock area — both for a brand new
  top-level area and for a user splitting a tab out into a new area).
- Produces: nothing consumed by later tasks — this is the final task.

**Why the handler defers with `QTimer.singleShot(0, ...)`:** ADS emits
`dockAreaCreated` from inside `CDockAreaWidget`'s own constructor (verified
against the upstream source,
`Qt-Advanced-Docking-System/src/DockAreaWidget.cpp`, `Q_EMIT
d->DockManager->dockAreaCreated(this)` runs right after the title bar/layout
are built) — **before** the dock widget that triggered the area's creation
has actually been inserted into it. Checking `area.dockWidgets()`
synchronously inside the slot would always see an empty area. Deferring to
the next event-loop turn lets the (synchronous, same call stack) insertion
finish first.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_panel_area_add_button.py`:

```python
def _add_button(area):
    return area.property("sciqlop_add_panel_button")


def test_plot_panel_area_gets_add_button(main_window, qtbot):
    panel = main_window.new_plot_panel()
    try:
        area = _area_for(main_window, panel)
        qtbot.waitUntil(lambda: _add_button(area) is not None, timeout=1000)
    finally:
        main_window.remove_panel(panel)


def test_second_panel_in_same_area_does_not_duplicate_button(main_window, qtbot):
    panel1 = main_window.new_plot_panel()
    try:
        area = _area_for(main_window, panel1)
        qtbot.waitUntil(lambda: _add_button(area) is not None, timeout=1000)
        first_button = _add_button(area)

        panel2 = main_window.new_native_plot_panel(area=area)
        try:
            qtbot.wait(50)
            assert _add_button(area) is first_button
        finally:
            main_window.remove_panel(panel2)
    finally:
        main_window.remove_panel(panel1)


def test_clicking_add_button_docks_new_panel_as_tab_in_same_area(main_window, qtbot):
    panel = main_window.new_plot_panel()
    try:
        area = _area_for(main_window, panel)
        qtbot.waitUntil(lambda: _add_button(area) is not None, timeout=1000)
        button = _add_button(area)
        before = area.dockWidgetsCount()

        button.click()
        qtbot.waitUntil(lambda: area.dockWidgetsCount() == before + 1, timeout=1000)

        new_panels = [p for p in main_window.plot_panels() if p is not panel]
        assert len(new_panels) == 1
        assert _area_for(main_window, new_panels[0]) is area
        main_window.remove_panel(new_panels[0])
    finally:
        main_window.remove_panel(panel)


def test_area_without_plot_panels_gets_no_add_button(main_window, qtbot):
    from PySide6.QtWidgets import QLabel
    from SciQLop.core.unique_names import auto_name, release_name

    name = auto_name(base="PlainDockTest")
    plain = QLabel("plain widget")
    plain.setWindowTitle(name)
    dw = QtAds.CDockWidget(name)
    dw.setWidget(plain)
    try:
        area = main_window.dock_manager.addDockWidget(
            QtAds.DockWidgetArea.BottomDockWidgetArea, dw)
        qtbot.wait(50)
        assert _add_button(area) is None
    finally:
        dw.closeDockWidget()
        plain.deleteLater()
        release_name(name)


def test_splitting_a_plot_panel_into_a_new_area_gets_its_own_add_button(main_window, qtbot):
    from SciQLop.components.plotting.ui.time_sync_panel import TimeSyncPanel
    from SciQLop.components.plotting.ui.panel_container import PanelContainer
    from SciQLop.core.unique_names import auto_name, release_name

    panel1 = main_window.new_plot_panel()
    try:
        area = _area_for(main_window, panel1)
        qtbot.waitUntil(lambda: _add_button(area) is not None, timeout=1000)

        name2 = auto_name(base="SplitTestPanel")
        panel2 = TimeSyncPanel(parent=None, name=name2, time_range=main_window.default_range)
        container2 = PanelContainer(panel2)
        dw2 = QtAds.CDockWidget(container2.windowTitle())
        dw2.setWidget(container2)
        try:
            new_area = main_window.dock_manager.addDockWidget(
                QtAds.DockWidgetArea.RightDockWidgetArea, dw2, area)
            qtbot.waitUntil(lambda: _add_button(new_area) is not None, timeout=1000)
            assert new_area is not area
        finally:
            dw2.closeDockWidget()
            container2.deleteLater()
            release_name(name2)
    finally:
        main_window.remove_panel(panel1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_panel_area_add_button.py -v`
Expected: the 5 new tests FAIL (`_add_button` always returns `None` — no
button is ever attached yet); the Task 2 test still passes.

- [ ] **Step 3: Implement**

In `SciQLop/core/ui/mainwindow.py`, in `_setup_dock_manager`
(`mainwindow.py:121-136`), add one line at the end of the method, right
after `self.dock_manager.setStyleSheet("")`:

```python
        self.dock_manager.setStyleSheet("")
        self.dock_manager.dockAreaCreated.connect(self._on_dock_area_created)
```

Then add two new methods immediately after `_drop_dead_panel_dock`
(currently ending at `mainwindow.py:469`):

```python
    def _on_dock_area_created(self, area: QtAds.CDockAreaWidget) -> None:
        # dockAreaCreated fires from inside CDockAreaWidget's constructor,
        # before the triggering dock widget has been inserted into it —
        # defer the plot-panel check to the next event-loop turn so
        # dockWidgets() is populated by the time we look.
        QtCore.QTimer.singleShot(0, lambda: self._ensure_add_panel_button(area))

    def _ensure_add_panel_button(self, area: QtAds.CDockAreaWidget) -> None:
        if not shiboken6.isValid(area):
            return
        if area.property("sciqlop_add_panel_button") is not None:
            return
        if not any(_extract_panel(dw) is not None for dw in area.dockWidgets()):
            return
        button = QtWidgets.QToolButton(area)
        button.setAutoRaise(True)
        button.setIcon(theme_icon("add_graph"))
        button.setToolTip(rich_tooltip(
            "New plot panel",
            "Add a new plot panel as a tab in this area."))
        button.clicked.connect(lambda: self.new_native_plot_panel(area=area))
        title_bar = area.titleBar()
        title_bar.insertWidget(title_bar.indexOf(title_bar.tabBar()) + 1, button)
        area.setProperty("sciqlop_add_panel_button", button)
```

No explicit teardown/disconnect is needed: the button is a child of `area`
and is destroyed with it; the `sciqlop_add_panel_button` property lives on
`area` itself, not in any external registry, so nothing dangles when an
area closes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_panel_area_add_button.py -v`
Expected: 6 passed (1 from Task 2 + 5 new).

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest --no-xvfb`
Expected: read the real pass/fail count and exit code — no new failures
compared to the pre-change baseline. If the machine can't sustain a full
`--no-xvfb` run (see project memory on RAM pressure during full-suite
runs), fall back to `uv run pytest tests/test_mainwindow_toolbar.py
tests/test_panel_area_add_button.py tests/test_panel_container.py
tests/test_vp_debug_layout.py -v` and say explicitly that the full suite
wasn't run.

- [ ] **Step 6: Commit**

```bash
git add SciQLop/core/ui/mainwindow.py tests/test_panel_area_add_button.py
git commit -m "feat(plotting): add a '+' button to dock areas holding plot panels"
```
