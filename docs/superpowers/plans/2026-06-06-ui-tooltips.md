# UI Tooltips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every accessible UI control a rich (bold title + description, optional shortcut) tooltip, applied inline via a single formatting helper.

**Architecture:** One pure helper `rich_tooltip()` in `SciQLop/core/ui/tooltips.py` formats Qt rich-text HTML. Each widget creation site calls it inline and passes the result to `setToolTip()`. Menus that host tooltipped actions call `setToolTipsVisible(True)` (Qt hides action tooltips in menus by default). Work is split into 5 tasks: the helper (TDD) + one task per UI surface.

**Tech Stack:** PySide6 (Qt 6), pytest, `html.escape` from the stdlib.

---

## Task 1: The `rich_tooltip` helper

**Files:**
- Create: `SciQLop/core/ui/tooltips.py`
- Test: `tests/test_tooltips.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tooltips.py`:

```python
from SciQLop.core.ui.tooltips import rich_tooltip


def test_title_only():
    assert rich_tooltip("New plot panel") == "<b>New plot panel</b>"


def test_title_and_body():
    assert rich_tooltip("New plot panel", "Create an empty panel.") == (
        "<b>New plot panel</b><br>Create an empty panel."
    )


def test_title_with_shortcut():
    assert rich_tooltip("Crosshair", shortcut="Ctrl+Shift+H") == (
        '<b>Crosshair</b> <span style="color:gray">(Ctrl+Shift+H)</span>'
    )


def test_title_body_and_shortcut():
    assert rich_tooltip("Crosshair", "Toggle crosshair.", "Ctrl+Shift+H") == (
        '<b>Crosshair</b> <span style="color:gray">(Ctrl+Shift+H)</span>'
        "<br>Toggle crosshair."
    )


def test_escapes_html_metacharacters():
    assert rich_tooltip("A & B", "x < y > z") == (
        "<b>A &amp; B</b><br>x &lt; y &gt; z"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tooltips.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'SciQLop.core.ui.tooltips'`

- [ ] **Step 3: Write minimal implementation**

Create `SciQLop/core/ui/tooltips.py`:

```python
from html import escape

__all__ = ["rich_tooltip"]


def rich_tooltip(title: str, body: str = "", shortcut: str = "") -> str:
    """Format a Qt rich-text tooltip: bold title + optional description + shortcut.

    Qt auto-detects HTML in tooltips, so returning tags is sufficient. Inputs
    are HTML-escaped defensively (they are static literals today, but escaping
    is cheap insurance against accidental markup breakage).
    """
    html = f"<b>{escape(title)}</b>"
    if shortcut:
        html += f' <span style="color:gray">({escape(shortcut)})</span>'
    if body:
        html += f"<br>{escape(body)}"
    return html
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tooltips.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add SciQLop/core/ui/tooltips.py tests/test_tooltips.py
git commit -m "feat(tooltips): add rich_tooltip formatting helper"
```

---

## Task 2: Phase 1 — Main toolbar & menus

**Files:**
- Modify: `SciQLop/core/ui/mainwindow.py` (toolbar action ~177-182, status toggle ~213-231, menus ~111-150, Plugin Store ~80-81)
- Modify: `SciQLop/components/profiling/menu.py` (Tools › Profiling submenu, ~22-38)

Background: `QMenu.addAction(text, slot)` returns the created `QAction` — capture it to set a tooltip. Each menu hosting tooltips needs `setToolTipsVisible(True)`.

- [ ] **Step 1: Add the import to `mainwindow.py`**

Near the other `from SciQLop.core.ui import ...` imports, add:

```python
from SciQLop.core.ui.tooltips import rich_tooltip
```

- [ ] **Step 2: Toolbar "Add new plot panel" action**

In `_setup_toolbar`, after `self.addTSPanel.setText("Add new plot panel")`, add:

```python
self.addTSPanel.setToolTip(rich_tooltip(
    "New plot panel",
    "Create an empty panel to drop products onto."))
```

- [ ] **Step 3: System-stats toggle (both states)**

In `_setup_status_bar`, replace:

```python
self._stats_toggle.setToolTip("Show system stats")
```

with:

```python
self._stats_toggle.setToolTip(rich_tooltip(
    "System stats",
    "Show live CPU, memory, and network usage."))
```

In `_toggle_stats`, replace:

```python
self._stats_toggle.setToolTip("Hide system stats" if visible else "Show system stats")
```

with:

```python
self._stats_toggle.setToolTip(rich_tooltip(
    "System stats",
    "Hide live usage stats." if visible else "Show live CPU, memory, and network usage."))
```

- [ ] **Step 4: View & Tools menus**

In `_setup_menus`, after `self.viewMenu = QMenu("View")` add `self.viewMenu.setToolTipsVisible(True)`, and after `self.toolsMenu = QMenu("Tools")` add `self.toolsMenu.setToolTipsVisible(True)`.

Replace the `Reload theme` action:

```python
self.viewMenu.addAction("Reload theme",
                        lambda: sciqlop_app().apply_theme(SciQLopStyle().color_palette))
```

with:

```python
reload_theme = self.viewMenu.addAction(
    "Reload theme",
    lambda: sciqlop_app().apply_theme(SciQLopStyle().color_palette))
reload_theme.setToolTip(rich_tooltip(
    "Reload theme",
    "Re-apply the current color palette and refresh all icons."))
```

Replace the `Open JupyterLab` action:

```python
self.toolsMenu.addAction("Open JupyterLab", self.open_jupyterlab_widget)
```

with:

```python
open_lab = self.toolsMenu.addAction("Open JupyterLab", self.open_jupyterlab_widget)
open_lab.setToolTip(rich_tooltip(
    "Open JupyterLab",
    "Open the embedded JupyterLab connected to this session's kernel."))
```

- [ ] **Step 5: Plugin Store, Open in browser, Logs actions**

Replace (in `_setup_ui`):

```python
self.toolsMenu.addAction("Plugin Store", self._show_appstore)
```

with:

```python
store = self.toolsMenu.addAction("Plugin Store", self._show_appstore)
store.setToolTip(rich_tooltip(
    "Plugin Store",
    "Browse and install community plugins."))
```

Replace (in `_setup_side_panels`):

```python
self.toolsMenu.addAction("Open JupyterLab in browser", wm.open_in_browser)
```

with:

```python
open_browser = self.toolsMenu.addAction("Open JupyterLab in browser", wm.open_in_browser)
open_browser.setToolTip(rich_tooltip(
    "Open JupyterLab in browser",
    "Open the JupyterLab server in your default web browser."))
```

Replace (in `_setup_side_panels`):

```python
self.viewMenu.addAction("Logs", self._show_logs)
```

with:

```python
logs = self.viewMenu.addAction("Logs", self._show_logs)
logs.setToolTip(rich_tooltip("Logs", "Show the application log panel."))
```

- [ ] **Step 6: Profiling submenu (`profiling/menu.py`)**

Add import at top: `from SciQLop.core.ui.tooltips import rich_tooltip`.

After the menu is created (where `self.menu = ...`), add `self.menu.setToolTipsVisible(True)`.

For the `Start trace…` and `Stop trace` actions, add tooltips right after each is created:

```python
self._start.setToolTip(rich_tooltip(
    "Start trace", "Begin recording a Perfetto performance trace."))
self._stop.setToolTip(rich_tooltip(
    "Stop trace", "Stop recording and save the current trace."))
```

(The `_open_last` and `_open_pick` actions already have plain tooltips — wrap them with `rich_tooltip(...)` keeping their existing text as the body and a short title, e.g. `rich_tooltip("Open last trace", "<existing text>")`.)

- [ ] **Step 7: Verify import & lint**

Run: `uv run python -c "import SciQLop.core.ui.mainwindow; import SciQLop.components.profiling.menu; print('ok')"`
Expected: `ok`

Run: `uv run flake8 SciQLop/core/ui/mainwindow.py SciQLop/components/profiling/menu.py`
Expected: no output (clean)

- [ ] **Step 8: Commit**

```bash
git add SciQLop/core/ui/mainwindow.py SciQLop/components/profiling/menu.py
git commit -m "feat(tooltips): rich tooltips on toolbar, View/Tools menus, profiling"
```

---

## Task 3: Phase 2 — Plot chrome & interactions

**Files:**
- Modify: `SciQLop/components/plotting/ui/crosshair_toggle.py` (~31-35)
- Modify: `SciQLop/components/plotting/ui/time_range_bar.py` (`_make_zoom_limit_combo` ~33-40, `_make_nav_button` ~43-47, pickers ~69-76)
- Modify: `SciQLop/components/plotting/ui/catalog_chrome.py` (mode combo ~11-14, target combo ~37-38)
- Modify: `SciQLop/components/plotting/ui/knob_inspector/section.py` (reset btn ~50)

- [ ] **Step 1: Crosshair toggle → rich**

In `crosshair_toggle.py`, add import `from SciQLop.core.ui.tooltips import rich_tooltip`.

Replace in `_refresh_appearance`:

```python
state = "on" if on else "off"
self.setToolTip(f"Crosshair and hover tooltip: {state} (Ctrl+Shift+H)")
```

with:

```python
state = "on" if on else "off"
self.setToolTip(rich_tooltip(
    "Crosshair & hover tooltip",
    f"Currently {state}. Shows a crosshair and value read-out as you move over plots.",
    "Ctrl+Shift+H"))
```

- [ ] **Step 2: Time-range bar — zoom limit, nav buttons, pickers**

In `time_range_bar.py`, add import `from SciQLop.core.ui.tooltips import rich_tooltip`.

Replace in `_make_zoom_limit_combo`:

```python
w.setToolTip("Maximum zoom-out range")
```

with:

```python
w.setToolTip(rich_tooltip(
    "Maximum zoom-out range",
    "Limits how far you can zoom out on the time axis."))
```

Change `_make_nav_button` to accept and set a tooltip:

```python
def _make_nav_button(text, parent, tooltip=""):
    b = QPushButton(text, parent)
    b.setFixedWidth(Metrics.em(2.5))
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if tooltip:
        b.setToolTip(tooltip)
    return b
```

Update the four nav-button creations in `__init__`:

```python
self._fast_backward_btn = _make_nav_button("|◀", self, rich_tooltip(
    "Jump back", "Move back by 5× the current duration."))
self._backward_btn = _make_nav_button("◀", self, rich_tooltip(
    "Step back", "Move back by one duration."))
self._forward_btn = _make_nav_button("▶", self, rich_tooltip(
    "Step forward", "Move forward by one duration."))
self._fast_forward_btn = _make_nav_button("▶|", self, rich_tooltip(
    "Jump forward", "Move forward by 5× the current duration."))
```

After `self._duration_combo = _make_duration_combo(self)` (in `__init__`), add:

```python
self._duration_combo.setToolTip(rich_tooltip(
    "Time window duration", "Length of the time range shown in this panel."))
self._start_picker.setToolTip(rich_tooltip(
    "Start time (UTC)", "Start of the time range shown in this panel."))
```

- [ ] **Step 3: Catalog chrome combos → rich**

In `catalog_chrome.py`, add import `from SciQLop.core.ui.tooltips import rich_tooltip`.

Replace:

```python
w.setToolTip("Catalog interaction mode")
```

with:

```python
w.setToolTip(rich_tooltip(
    "Catalog interaction mode",
    "How clicks on this panel interact with catalog events."))
```

Replace:

```python
self._target_combo.setToolTip("Target catalog for new events")
```

with:

```python
self._target_combo.setToolTip(rich_tooltip(
    "Target catalog",
    "Catalog that newly created events are added to."))
```

- [ ] **Step 4: Knob inspector reset button → rich**

In `knob_inspector/section.py`, add import `from SciQLop.core.ui.tooltips import rich_tooltip`.

Replace:

```python
self._reset_btn.setToolTip("Reset all parameters to defaults")
```

with:

```python
self._reset_btn.setToolTip(rich_tooltip(
    "Reset parameters", "Restore all parameters in this section to their defaults."))
```

(Leave the `w.setToolTip(spec.description)` per-knob tooltip as-is — `spec.description` is dynamic data, not a static UI label.)

- [ ] **Step 5: Verify import & lint**

Run: `uv run python -c "import SciQLop.components.plotting.ui.crosshair_toggle, SciQLop.components.plotting.ui.time_range_bar, SciQLop.components.plotting.ui.catalog_chrome, SciQLop.components.plotting.ui.knob_inspector.section; print('ok')"`
Expected: `ok`

Run: `uv run flake8 SciQLop/components/plotting/ui/crosshair_toggle.py SciQLop/components/plotting/ui/time_range_bar.py SciQLop/components/plotting/ui/catalog_chrome.py SciQLop/components/plotting/ui/knob_inspector/section.py`
Expected: no output

- [ ] **Step 6: Commit**

```bash
git add SciQLop/components/plotting/ui/crosshair_toggle.py SciQLop/components/plotting/ui/time_range_bar.py SciQLop/components/plotting/ui/catalog_chrome.py SciQLop/components/plotting/ui/knob_inspector/section.py
git commit -m "feat(tooltips): rich tooltips on plot chrome (crosshair, time bar, catalog chrome, knobs)"
```

---

## Task 4: Phase 3 — Catalog browser

**Files:**
- Modify: `SciQLop/components/catalogs/ui/catalog_browser.py` (add/delete/columns/attribute buttons ~213-231)
- Modify: `SciQLop/components/catalogs/ui/column_visibility_popover.py` (show/hide/reset buttons ~52-54)

- [ ] **Step 1: Catalog browser buttons**

In `catalog_browser.py`, add import `from SciQLop.core.ui.tooltips import rich_tooltip`.

Add a tooltip to the add-event button (after it is created, near `self._add_event_btn.clicked.connect(...)`):

```python
self._add_event_btn.setToolTip(rich_tooltip(
    "Add event", "Create a new event in the target catalog."))
```

Add to the delete button:

```python
self._delete_btn.setToolTip(rich_tooltip(
    "Delete", "Delete the selected events from the catalog."))
```

Replace the plain `_columns_btn` tooltip:

```python
self._columns_btn.setToolTip("Show / hide / reorder columns")
```

with:

```python
self._columns_btn.setToolTip(rich_tooltip(
    "Columns", "Show, hide, or reorder the event-table columns."))
```

Replace the plain `_add_attr_btn` tooltip:

```python
self._add_attr_btn.setToolTip("Add a new metadata attribute to the selected events (or all events if no selection)")
```

with:

```python
self._add_attr_btn.setToolTip(rich_tooltip(
    "Add attribute",
    "Add a metadata attribute to the selected events (or all events if none are selected)."))
```

- [ ] **Step 2: Column-visibility popover buttons**

In `column_visibility_popover.py`, add import `from SciQLop.core.ui.tooltips import rich_tooltip`.

After the three buttons are created (~line 54), add:

```python
self._show_all_btn.setToolTip(rich_tooltip("Show all", "Make every column visible."))
self._hide_all_btn.setToolTip(rich_tooltip(
    "Hide all", "Hide every column except frozen ones."))
self._reset_btn.setToolTip(rich_tooltip(
    "Reset", "Restore the default column visibility and order."))
```

- [ ] **Step 3: Verify import & lint**

Run: `uv run python -c "import SciQLop.components.catalogs.ui.catalog_browser, SciQLop.components.catalogs.ui.column_visibility_popover; print('ok')"`
Expected: `ok`

Run: `uv run flake8 SciQLop/components/catalogs/ui/catalog_browser.py SciQLop/components/catalogs/ui/column_visibility_popover.py`
Expected: no output

- [ ] **Step 4: Commit**

```bash
git add SciQLop/components/catalogs/ui/catalog_browser.py SciQLop/components/catalogs/ui/column_visibility_popover.py
git commit -m "feat(tooltips): rich tooltips on catalog browser controls"
```

---

## Task 5: Phase 4 — Product search & context menu

**Files:**
- Modify: `SciQLop/components/plotting/ui/product_search_overlay.py` (search box ~66-67)
- Modify: `SciQLop/components/products/product_context_menu.py` (menu actions ~49-60)

Note: the product **tree** widget (`ProductsView`) is provided by the C++ `SciQLopPlots` library and is out of scope for this repo (do not edit SciQLopPlots). This task covers the in-tree Python product widgets only.

- [ ] **Step 1: Product search box tooltip**

In `product_search_overlay.py`, add import `from SciQLop.core.ui.tooltips import rich_tooltip`.

After:

```python
self._search_box.setPlaceholderText("Search products (e.g. MMS FGM, ACE MAG B_gsm)…")
```

add:

```python
self._search_box.setToolTip(rich_tooltip(
    "Search products",
    "Filter the product tree by name, mission, or instrument."))
```

- [ ] **Step 2: Product context menu — enable tooltips + label the panel actions**

In `product_context_menu.py`, add import `from SciQLop.core.ui.tooltips import rich_tooltip`.

After the top-level `menu` is created (before actions are added), enable tooltips:

```python
menu.setToolTipsVisible(True)
```

For the per-panel submenu (inside the `for panel_name in panels:` loop), after `panel_menu = menu.addMenu(panel_name)` add:

```python
panel_menu.setToolTipsVisible(True)
```

Replace the `+ New plot` action (line ~56-57):

```python
panel_menu.addAction("+ New plot",
                     lambda p=panel, pp=product_path: plot_product(p, pp, plot_type=PlotType.TimeSeries))
```

with:

```python
new_plot = panel_menu.addAction(
    "+ New plot",
    lambda p=panel, pp=product_path: plot_product(p, pp, plot_type=PlotType.TimeSeries))
new_plot.setToolTip(rich_tooltip(
    "New plot in this panel", "Add this product as a new plot in the panel."))
```

Replace the `+ New panel` action (line ~60):

```python
menu.addAction("+ New panel", lambda pp=product_path: _plot_in_new_panel(pp, main_window))
```

with:

```python
new_panel = menu.addAction(
    "+ New panel", lambda pp=product_path: _plot_in_new_panel(pp, main_window))
new_panel.setToolTip(rich_tooltip(
    "New panel", "Open this product in a brand-new plot panel."))
```

- [ ] **Step 3: Verify import & lint**

Run: `uv run python -c "import SciQLop.components.plotting.ui.product_search_overlay, SciQLop.components.products.product_context_menu; print('ok')"`
Expected: `ok`

Run: `uv run flake8 SciQLop/components/plotting/ui/product_search_overlay.py SciQLop/components/products/product_context_menu.py`
Expected: no output

- [ ] **Step 4: Commit**

```bash
git add SciQLop/components/plotting/ui/product_search_overlay.py SciQLop/components/products/product_context_menu.py
git commit -m "feat(tooltips): rich tooltips on product search and context menu"
```

---

## Final verification

- [ ] Run the helper unit tests: `uv run pytest tests/test_tooltips.py -v` → all pass.
- [ ] Run flake8 on every touched file → clean.
- [ ] **Manual smoke** (author): `uv run sciqlop`, then hover the toolbar, open the View/Tools menus, hover the time-range bar / crosshair toggle / catalog chrome, open a catalog and hover its buttons, open the product search and right-click a product. Confirm every tooltip shows a bold title + description.
