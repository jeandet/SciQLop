# Reclaim toolbar space: hidden-by-default toolbar + per-panel-area "+" tab button

**Date:** 2026-07-14
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — `SciQLop/core/ui/mainwindow.py`, new small
helper module under `SciQLop/components/plotting/`).

## Problem

The top toolbar (`SciQLopMainWindow.toolBar`, `mainwindow.py:215-231`) is a
full-width horizontal bar that today carries SciQLop's own single "Add new
plot panel" action plus, via the documented plugin integration surface
(`main_window.toolBar`), a handful of icon actions from external plugins
(sismo, radio, cdf_workbench dock-toggle actions; msa's quicklook button).
For what it currently holds, a persistent full-width bar wastes vertical
space that could go to plotting.

`main_window.toolBar` is a **published plugin API** — four plugins in the
separate `plugins_sciqlop` repo call `.addAction()`/`.addWidget()` on it
directly and are documented to do so
(`docs/superpowers/specs/2026-03-12-sciqlop-plugin-dev-skill-design.md:136-137`).
Any redesign must not break them without a coordinated cross-repo change,
which is out of scope here.

A persistent vertical icon rail is also rejected as a replacement: SciQLop
already has an auto-hide side-panel rail (`add_side_pan`, left edge —
Products, Catalogs, Settings, Properties, Chat) and a second rail next to it
would look redundant.

Separately, "Add new plot panel" being toolbar-only means creating a second
panel next to an existing one requires reaching for the (now de-prioritized)
toolbar rather than acting where the user already is — on the panel itself.

## Design

### Part 1 — Toolbar becomes hidden-by-default, not removed

`self.toolBar` keeps its current identity, position, and area
(`TopToolBarArea`, set up in `_setup_toolbar`, `mainwindow.py:215-231`) —
this is what makes it a no-op change for plugin code. The only changes:

1. After `_setup_toolbar()` builds the bar, call `self.toolBar.setVisible(False)`.
2. Add a checkable entry to the existing `View` menu (`self.viewMenu`,
   `mainwindow.py:144-152`) wired to `self.toolBar.toggleViewAction()` —
   `QToolBar` provides this action natively, and it already keeps its checked
   state in sync with visibility, including if the user re-hides the toolbar
   by dragging its close affordance.
3. SciQLop's own "Add new plot panel" action (`self.addTSPanel`) stays in the
   toolbar as a spare, low-cost entry point (it costs nothing while hidden).
   The quickstart-shortcut registration
   (`sciqlop_app().add_quickstart_shortcut(...)`, `mainwindow.py:230-231`)
   is untouched — it's a separate, always-visible welcome-page affordance,
   not part of the toolbar.

No plugin in `plugins_sciqlop` needs to change: `main_window.toolBar` is
still a real, addressable `QToolBar` that accepts `.addAction()` /
`.addWidget()`; it simply starts hidden and the user opts back in via
`View > Show toolbar`.

### Part 2 — "+" button next to each plot-panel area's tabs

**Goal:** from any plot panel, one click creates a new plot panel as another
tab in that same dock area — the primary way to grow a layout, replacing the
toolbar button for this specific action.

**Tagging plot panels.** `new_native_plot_panel` (`mainwindow.py:445-458`)
sets a dynamic property on the `CDockWidget` it creates, e.g.
`dock_widget.setProperty("sciqlop_plot_panel", True)`, right before docking
it. This distinguishes plot-panel dock widgets from side panels (Products,
Catalogs, Settings, Properties, Chat — added via `add_side_pan`'s auto-hide
sidebar, a different ADS mechanism entirely) and from the welcome page.

**Attaching the button.** Connect once, in `_setup_dock_manager`, to
`self.dock_manager.dockAreaCreated` (`Signal(ads::CDockAreaWidget*)`, fires
for every new dock area — both areas created directly by docking and areas
created when the user drags a tab out to split an existing area). The
handler:

1. Skips the area if it has already been given a button (guard via a
   property on the area itself, e.g. `area.property("sciqlop_has_add_button")`).
2. Skips the area if none of its current dock widgets carry the
   `sciqlop_plot_panel` property.
3. Otherwise builds a small `QToolButton` ("+", themed icon, tooltip "New
   plot panel here") and inserts it into the area's title bar via
   `area.titleBar().insertWidget(index, button)`, positioned immediately
   after the tab strip (`titleBar().tabBar()`) and before the area's other
   title-bar buttons (auto-hide/undock/close). Marks the area as handled.

This is intentionally reactive rather than tied only to the initial
docking call — it means a plot panel that ends up in a *new* area because
the user dragged its tab out to split the layout gets its own "+" for free,
with no separate split-handling code path.

**Click behavior.** The button's handler creates a new plot panel
(`new_native_plot_panel`'s panel-construction logic) and docks it into the
*same* area as an additional tab — using QtAds's tab-into-area API
(`dock_manager.addDockWidgetTabToArea(new_dock_widget, area)`) rather than
the default `TopDockWidgetArea` used by `addWidgetIntoDock` today. The new
dock widget is tagged `sciqlop_plot_panel` exactly like any other plot panel,
same as the toolbar/command-palette/quickstart-tile paths.

**Out of scope for this change:** a plot panel being dragged into an
*existing* non-plot area (rather than splitting into a new one) doesn't
retrofit a "+" onto that area. This is a narrow, unusual case (there is no
common existing area for a plot panel to land in besides other plot-panel
areas or the welcome page, which is normally replaced/closed once panels
exist) and is left unhandled; if it becomes a real workflow, add a check in
`dockWidgetAdded` as a follow-up.

**Addendum (2026-07-14, later same day):** the "only if the area already
holds a plot panel" gate described above (and the corresponding "welcome
page never receives an add-button" regression test) was removed the same
day, per a follow-up request that the "+" be a general "create a plot panel
here" affordance rather than one gated on existing content — this was most
visible as the welcome page never getting a "+" until a first plot panel
had been created elsewhere. `_ensure_add_panel_button` now attaches to
*every* area that reaches it via `dockAreaCreated`/the direct call, with no
content check. Side panels (Products/Catalogs/Settings/Properties/Chat)
remain excluded — not by that check, but structurally: they're added via
`addAutoHideDockWidget`, which never constructs a `CDockAreaWidget` or fires
`dockAreaCreated` at all (confirmed by reading `DockManager.cpp`/
`DockContainerWidget.cpp` in the QtAds source), so they never reach
`_ensure_add_panel_button` in the first place. See the handover doc's
"Session 2" section for the real segfault this change surfaced in
*existing* test teardown code (not new code) and its fix.

### Entry points for creating a plot panel, after this change

1. **"+" button** on any dock area already holding plot panels — new,
   primary path, works for both the first extra panel and split-created
   areas.
2. **Command palette** — "New plot panel" (`components/command_palette/commands.py:21,56`),
   unchanged.
3. **Welcome page quickstart tile** — unchanged, still the way to create the
   very first panel in an empty workspace (no plot-panel area exists yet for
   a "+" to live on).
4. **Toolbar button** — kept as a spare, reachable via `View > Show toolbar`.

## Testing

- Toolbar: a test asserting `main_window.toolBar.isVisible()` is `False`
  right after main-window construction, and that toggling the new View-menu
  action flips it to `True` (and back).
- "+" button: construct a plot panel, assert its dock area exposes exactly
  one add-button; add a second plot panel via the toolbar/command palette
  into the *same* area (simulating a user's existing workflow) and assert no
  duplicate button appears; click the add-button and assert a new panel is
  docked as a tab in the same area (panel count in that area increments,
  area identity unchanged).
- Split case: dock two panels into one area, drag/simulate splitting one
  into a new area (or construct the equivalent via QtAds APIs directly in
  the test if drag simulation is impractical), assert the new area also
  exposes an add-button.
- Regression: side-panel areas (Products/Catalogs/Settings/Properties/Chat)
  and the welcome page never receive an add-button.
