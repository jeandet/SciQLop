# First-plot onboarding: guided coach-mark tour

**Date:** 2026-07-14
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — new component `SciQLop/components/onboarding/`,
small hooks into `SciQLop/core/ui/mainwindow.py` and the Welcome page).

## Problem

A first-time user (target persona: a space-physics bachelor student or
researcher, no prior SciQLop exposure) lands on the Welcome page and has no
way to discover the sequence needed to produce their first plot. Nothing on
screen teaches:

1. That an empty plot panel is one click away (a "+" button already exists
   on the Welcome page's own dock area from the very first frame, per
   `docs/superpowers/specs/2026-07-14-toolbar-and-panel-tabs-design.md`).
2. That the Products browser — where every plottable dataset lives — is a
   **collapsed, icon-only auto-hide side-tab** (`add_side_pan`,
   `mainwindow.py:170-173`), invisible until clicked.
3. That a product reaches a panel either by dragging it onto the panel, or,
   more directly, via right-click → **"+ New panel"** in the product tree's
   context menu (`components/products/product_context_menu.py:70-79`), which
   creates the panel and plots the product in one action.

This is a pure discoverability gap — every mechanism already exists and
works; nothing currently points a new user at it. This design adds a
one-time guided tour (replayable on demand) that walks a first-time user
through creating a panel, finding the Products browser, and plotting a real
product, ending with a tip about the one-click shortcut.

## Design

### Component layout

New self-contained component, following the existing `backend/` + `ui/`
convention used by other components:

```
SciQLop/components/onboarding/
  backend/
    settings.py     # OnboardingSettings(ConfigEntry)
    tour.py         # tour steps as data + target-resolution helpers
  ui/
    coach_mark.py    # the spotlight overlay widget
    tour_controller.py  # walks the step list against a live main window
```

### Settings

```python
class OnboardingSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Onboarding"
    tour_completed: bool = False
```

Global, not per-workspace — matches "first-time SciQLop user", not
"first-time in this workspace".

### Tour steps as data

The tour is a plain list of step records (dataclass or pydantic model), not
a hand-rolled state machine, per the project's "data over code" preference:

```python
@dataclass
class TourStep:
    title: str
    body: str
    resolve_target: Callable[[SciQLopMainWindow], QWidget | None]
    wait_for_completion: Callable[[SciQLopMainWindow, Signal-ish], Awaitable[bool]]
    timeout_s: float | None = None
    on_timeout: Literal["abort", "advance"] = "advance"
```

Four steps:

| # | Target | Copy | Completes when | Timeout behavior |
|---|--------|------|-----------------|-------------------|
| 1 | "+" button on the dock area title bar holding the Welcome page | "Click here to create your first plot panel." | A new plot-panel dock widget appears (`sciqlop_plot_panel` property set) | none |
| 2 | Collapsed Products auto-hide side-tab icon | "Your data lives here — click to open the Products browser." | The Products dock widget becomes visible | none |
| 3 | First resolvable candidate from a priority list of well-known products (e.g. MMS1 FGM B_GSE, with 1-2 fallbacks) in the product tree | "Drag this onto your empty panel to plot it." | A graph appears in the panel created at step 1 | ~10s bounded poll; on failure, **abort the whole tour** with: "Looks like data providers aren't ready yet — replay this tour anytime from Tools → Replay Onboarding Tour once you're online." |
| 4 | Products tree generally (no specific node) | "Tip: next time, right-click any product → '+ New panel' to create a panel and plot it in one click." | User clicks "Got it" | none |

Steps 1-2 always complete (their targets exist unconditionally). Only step
3 depends on external state (a data provider populating the tree), so only
step 3 has an abort path — an offline user still gets the panel-creation and
Products-discovery lessons before the tour ends early.

**Target resolution for step 3** is a small resolver trying each candidate
`(mission, dataset, parameter)` path against the live product tree in
priority order and highlighting whichever resolves first — avoids hardcoding
a single brittle path across differing speasy/provider configurations.

**Skip/dismiss:** every step shows a small "Skip tour" link; `Esc` closes the
whole tour immediately. Either path sets `tour_completed = True` (won't
auto-fire again) but does not block replay via menu or Welcome page.

### Overlay widget (`coach_mark.py`)

A single frameless, translucent `QWidget`, sized to the main window,
repainted per step:

- Full-window dim overlay with a rounded-rect cutout mapped from the current
  target widget's `geometry()` → `mapToGlobal()`.
- A small info bubble (title, body, Skip link) anchored beside the cutout,
  flipping side automatically if it would render off-screen.
- Repositions on the target widget's `resize`/`move` and on main-window
  resize, so it survives layout changes mid-tour.

### Controller (`tour_controller.py`)

Walks the step list against a live `SciQLopMainWindow`: resolves the current
step's target, shows the overlay, awaits that step's completion signal
(wired via `signal.connect(context, slot)` per
`docs/qt-lifetime-patterns.md`, never a bare closure over `self._plot`-style
references), advances, or aborts per the step's timeout policy.

**Qt lifetime safety:** the controller never touches a target widget from
inside its own `destroyed` slot; if a target (e.g. the panel created in step
1) is closed by the user mid-tour, that step's wait aborts gracefully rather
than dereferencing a dead pointer — this is the exact class of bug flagged
in `docs/qt-lifetime-patterns.md` and the SIGSEGV precedent in commit
`293a7afa`.

### Trigger points

All three call the same `run_tour(main_window)`:

1. **Automatic first-ever launch** — checked via
   `OnboardingSettings().tour_completed`, fired shortly after the main
   window is shown and the workspace is loaded (mirrors how other
   post-startup hooks are sequenced today).
2. **Welcome page quickstart card** — "Take the tour", registered the same
   way as the existing "Plot panel" quickstart tile
   (`sciqlop_app().add_quickstart_shortcut(...)`).
3. **Tools menu entry** — "Replay Onboarding Tour", added to the existing
   `self.toolsMenu` (`mainwindow.py:157`) — no new top-level menu.

Both manual triggers run regardless of `tour_completed`'s value.

## Error handling

- Step 3 network/provider unavailability: bounded retry (~10s), then abort
  with a clear message pointing at the replay entry point — never a silent
  hang or an unexplained tour disappearance.
- Any target widget destroyed mid-tour: that step aborts gracefully (no
  crash), following the documented Qt lifetime pattern.
- Main window closed/app quitting mid-tour: overlay is a child widget of the
  main window (or otherwise parented) so normal Qt teardown handles it; no
  separate cleanup path needed.

## Testing

- Auto-launch fires when `tour_completed` is unset; does not when set.
- Each step's overlay cutout geometry matches its resolved target widget's
  screen geometry.
- Each completion condition, simulated via `qtbot`: creating a panel via the
  step-1 button, expanding the Products dock, calling `plot_product()` for
  the step-1 panel — assert the controller advances past that step.
- Step-3 timeout path: mock the target resolver to return no candidates,
  assert the tour aborts with the expected message and `tour_completed`
  still ends up `True`.
- Skip/Esc at each step closes the overlay cleanly with no dangling QObject
  (regression-guards the `293a7afa`-class segfault pattern).
- Welcome-page card and Tools-menu entry both invoke `run_tour()` and work
  as replay even when `tour_completed` is already `True`.
