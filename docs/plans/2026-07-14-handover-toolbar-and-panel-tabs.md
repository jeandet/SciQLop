# Handover — toolbar relocation + panel-area "+" button

**Branch:** `main`
**Last commit:** `946cf626 fix(plotting): attach add-panel button on direct dock too, fix split-test teardown`
**Pushed:** yes, to `jeandet/main` (0 commits ahead as of this handover)
**Tests:** 7 of 8 new tests in `tests/test_panel_area_add_button.py` confirmed passing via a real `uv run pytest --no-xvfb` run, plus all 3 tests in `tests/test_mainwindow_toolbar.py` and the pre-existing `test_new_native_plot_panel_docks_into_explicit_area`. The 8th
(`test_splitting_a_plot_panel_into_a_new_area_gets_its_own_add_button`) has its underlying segfault fixed but has **not** had a second clean confirming run — see "What's NOT verified" below. No full-suite run attempted (out of scope, separate known issue).

## What was shipped this session

7 commits on top of `d2147cbf` (jupyqt 0.6.1→0.6.2 bump):

- `81ee617c` `docs(superpowers): add toolbar-and-panel-tabs design spec`
  → `docs/superpowers/specs/2026-07-14-toolbar-and-panel-tabs-design.md`
- `976b5abf` `feat(mainwindow): hide toolbar by default, toggle from View menu`
  → `self.toolBar.setVisible(False)` + `self.viewMenu.addAction(self.toolBar.toggleViewAction())` in `_setup_toolbar` (`SciQLop/core/ui/mainwindow.py`). Same `QToolBar` object, same position — the 4 external plugins (sismo, radio, cdf_workbench, msa in the separate `plugins_sciqlop` repo) that call `main_window.toolBar.addAction()`/`.addWidget()` need zero changes.
- `72f1c5fc` `feat(mainwindow): let new_native_plot_panel target an explicit dock area`
  → `new_native_plot_panel(name=None, area=None)` threads `area` into the pre-existing `addWidgetIntoDock(..., area=area, ...)`.
- `af5560f0` `feat(plotting): add a '+' button to dock areas holding plot panels`
  → `_setup_dock_manager` connects `dock_manager.dockAreaCreated` to `_on_dock_area_created`, which defers (`QTimer.singleShot(0, ...)`) to `_ensure_add_panel_button` — load-bearing deferral because ADS fires `dockAreaCreated` from inside `CDockAreaWidget`'s constructor, *before* the triggering dock widget is inserted.
- `c5ee2826` `fix(tests): compare plot panels by name, not object, in add-button click test`
  → final-review catch: a test compared `main_window.plot_panels()` (`List[str]`) against a `TimeSyncPanel` object via `is not` — never filtered correctly.
- `fc04ae96` `docs(superpowers): add toolbar-and-panel-tabs implementation plan`
  → `docs/superpowers/plans/2026-07-14-toolbar-and-panel-tabs.md` (was written earlier in the session but not committed until here).
- `946cf626` `fix(plotting): attach add-panel button on direct dock too, fix split-test teardown`
  → **the two bugs found by actually running the tests**, see next section.

## Architecture cheat-sheet

```
_setup_dock_manager()
  └─ dock_manager.dockAreaCreated.connect(_on_dock_area_created)
        └─ QTimer.singleShot(0, _ensure_add_panel_button(area))   # deferred: see comment in code
              └─ guards: shiboken6.isValid(area), no existing button,
                 any(_extract_panel(dw) is not None for dw in area.dockWidgets())
              └─ attaches QToolButton to area.titleBar(), right after tabBar()
              └─ button.clicked → new_native_plot_panel(area=area)

new_native_plot_panel(name=None, area=None)
  └─ addWidgetIntoDock(..., area=area, ...)     # area=None → old auto-pick-biggest-area behavior
  └─ ALSO calls _ensure_add_panel_button(dock_widget.dockAreaWidget()) directly, synchronously
     (needed because addWidgetIntoDock commonly TABS into an *existing* area —
      e.g. the welcome page's, already open at startup — which never fires dockAreaCreated)
```

Two attach paths, both required:
1. **Direct, synchronous call** in `new_native_plot_panel` — covers the common case (new panel joins an existing area, most often the welcome page's).
2. **`dockAreaCreated` signal, deferred** — covers the case where ADS actually constructs a brand-new area (first panel ever with nothing pre-existing, or a user splitting a tab out into a new area).

## Real bugs found only by running the tests (not by static review)

Both implementer + reviewer subagents reviewed this code by careful reading only (a container/WebEngine environment issue was, wrongly, initially treated as making live tests impossible — see "Process note" below). Once `--no-xvfb` actually got tests running, two real bugs surfaced that the static review missed entirely:

1. **Missing direct-attach path.** Originally `_ensure_add_panel_button` was wired *only* to `dockAreaCreated`. Since the welcome page's dock area is already open at startup, the very first plot panel a user creates joins that *existing* area via `_find_biggest_area()` → `addDockWidgetTabToArea` — which never fires `dockAreaCreated`. Result: the "+" button silently never appeared for the single most common case. Fixed by also calling `_ensure_add_panel_button` directly right after `addWidgetIntoDock` returns (no `QTimer` needed there — the widget is already inserted by then).
2. **Lifetime bug in the split test's manual teardown.** `test_splitting_a_plot_panel_into_a_new_area_gets_its_own_add_button` builds a `CDockWidget` by hand (bypassing `addWidgetIntoDock`) and tore it down with `dw2.closeDockWidget(); container2.deleteLater()` — missing the `dw2.takeWidget()` step that the codebase's own `remove_panel`/`remove_native_plot_panel` always do first. Left `dw2` holding a dangling pointer into freed memory, segfaulting the next `plot_panels()` call. Fixed by adding `dw2.takeWidget()` before `closeDockWidget()`.

## What's NOT verified

`test_splitting_a_plot_panel_into_a_new_area_gets_its_own_add_button` — the segfault is fixed (the fix is a straightforward, exact match to an established codebase pattern), but there's no second clean confirming run. `main_window` fixture cold-start became intermittently hang-prone partway through this session (three separate fresh invocations timed out at 60s/90s/180s, with zero CPU/RAM pressure observed) — see [[pitfall-mainwindow-fixture-cold-start-hang]] in project memory. **Get one clean run of this test (and ideally the two new test files in full) via CI or on a calmer host before treating this fully verified.**

No full-suite run was attempted — out of scope for this feature and a separately known-flaky area of this project's test infra.

## Process note (for whoever picks this up)

Early in this session I hit the WebEngine-fatal-abort failure mode on the *default* (xvfb-enabled) pytest invocation, did real forensic work (`coredumpctl`, ruling out RAM pressure, confirming it on untouched pre-existing files) and escalated to the user as an apparently unfixable environment blocker — all before trying `uv run pytest --no-xvfb`, which was already documented in project memory (`feedback_check_memories_first.md`, `feedback_pytest_ram_monitor.md`) as the canonical fix. Once tried, it worked, and immediately surfaced the two real bugs above. Both memories have been updated with this recurrence. **Try `--no-xvfb` first, before any forensic tooling, every time.**

## Things to watch / pre-flight checks

- If you touch `_ensure_add_panel_button` or `_on_dock_area_created` again: remember there are *two* call paths (direct + signal), both load-bearing — see architecture cheat-sheet above. Removing either one silently breaks a real case.
- If you add more manual `CDockWidget` construction in tests (bypassing `addWidgetIntoDock`), always mirror the `takeWidget()` → `closeDockWidget()` → `deleteLater()` teardown order used everywhere else in `mainwindow.py`.
- `main_window.toolBar` is a documented external-plugin API (`plugins_sciqlop` repo: sismo, radio, cdf_workbench, msa) — any future change to how the toolbar is exposed must keep `self.toolBar` a real, addressable `QToolBar`.

## To pick up next

1. Get a clean confirming pytest run of the split-area test (and ideally the full new-test files) via CI or a calmer host.
2. Nothing else outstanding for this feature — it's functionally complete and pushed.
