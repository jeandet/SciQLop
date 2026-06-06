# Rich tooltips across the UI

**Date:** 2026-06-06
**Status:** Approved, ready for implementation plan

## Goal

Document every accessible UI control with a helpful tooltip so users
understand what each action, button, and toggle does. Today only ~20
tooltips exist across the app while there are ~47 actions and ~30 buttons,
so coverage is thin and inconsistent.

Tooltips are **rich**: a bold action title followed by a short sentence of
explanation, with the keyboard shortcut shown where one exists (extending
the existing convention from the crosshair toggle).

## Non-goals

- No central tooltip catalog / i18n layer (rejected: breaks locality of
  reasoning — see Approach below).
- No exhaustive per-string tests (copy churn, no value).
- No new tooltip-on-plot behaviour — per-graph hover info stays on the
  inspector tree row, never on the plot widget (existing rule).

## Approach

**Formatting helper + inline text** (Approach A of the brainstorm).

A single helper formats every tooltip consistently; the actual copy lives
as plain string literals next to the widget it describes. This keeps
locality of reasoning (the text is where the widget is, visible in review)
while the helper gives the data-over-code win where it matters: consistent
formatting, restyleable in one place.

Rejected alternatives:
- **Central catalog (data file of keys → text):** all copy in one place,
  but you must chase a key to another file to know what a widget says, and
  keys drift from widgets. Loses locality.
- **Hybrid (per-module constants):** middle ground, extra ceremony for no
  real benefit here.

## Components

### 1. Formatting helper — `SciQLop/core/ui/tooltips.py`

```python
def rich_tooltip(title: str, body: str = "", shortcut: str = "") -> str:
    """Qt rich-text tooltip: bold title + optional description + shortcut.

    Qt auto-detects HTML in tooltips, so returning tags is sufficient.
    Inputs are escaped defensively (they are static literals today, but
    escaping is cheap insurance and keeps the helper honest).
    """
```

Behaviour:
- `rich_tooltip("New plot panel")` → `<b>New plot panel</b>`
- `rich_tooltip("New plot panel", "Create an empty panel to drop products onto.")`
  → `<b>New plot panel</b><br>Create an empty panel to drop products onto.`
- `shortcut` is rendered as a dimmed suffix on the title line (matching the
  existing `... (Ctrl+Shift+H)` convention).
- `&`, `<`, `>` in inputs are HTML-escaped.

One unit, one purpose. This is the only piece with a unit test.

### 2. Application sites (inline copy)

Each phase is independently verifiable and committable.

**Phase 1 — Main toolbar & menus** (`SciQLop/core/ui/mainwindow.py`)
- Toolbar: Add new plot panel; system-stats toggle (already plain → rich).
- Menus: Plugin Store, Open JupyterLab, Open JupyterLab in browser,
  Reload theme, Logs, and any other menu actions present.
- Call `setToolTipsVisible(True)` on each menu that hosts tooltipped
  actions — Qt hides `QAction` tooltips in menus by default. Goal is to
  document **all** accessible UI, menus included.

**Phase 2 — Plot chrome & interactions** (`SciQLop/components/plotting/ui/`)
- `time_range_bar.py` (zoom-limit control — already plain → rich),
- `crosshair_toggle.py` (already plain → rich),
- `catalog_chrome.py`,
- knob inspector / graph-context inspector controls.

**Phase 3 — Catalog browser** (`SciQLop/components/catalogs/ui/`)
- Upgrade existing plain tooltips (columns button, add-attribute button)
  to rich, plus tree controls, save/dirty indicators, column-visibility
  popover controls.

**Phase 4 — Product tree & search** (`SciQLop/components/products/`,
product search overlay)
- Product browser controls, search field, and drag-and-drop hints where a
  widget exists to host them.

## Data flow

None beyond a pure function call: each widget creation site calls
`rich_tooltip(...)` and passes the result to `widget.setToolTip(...)` /
`action.setToolTip(...)`. No state, no signals, no persistence.

## Error handling

Not applicable — `rich_tooltip` is a pure string transform over static
literals. Escaping prevents accidental markup breakage.

## Testing

- **`tests/test_tooltips.py`** — unit-test `rich_tooltip`: bold-only,
  title+body, shortcut suffix, HTML-escaping of `&` / `<`.
- **Manual verification** — the author will hover each surface to confirm
  coverage and copy quality. No automated coverage smoke test (copy is not
  logic; asserting it churns without catching real regressions).

## Out-of-scope follow-ups

- i18n / translation of tooltip copy.
- Tooltips for dynamically generated plugin UI not owned by this repo.
