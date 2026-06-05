# Startup & Welcome Quickstart UX — Design

**Date:** 2026-06-05
**Status:** Approved (design), pending implementation plan

Two independent UX improvements to SciQLop's startup and welcome experience:

- **A. Reopen last workspace on startup** — a setting (default **on**) so SciQLop resumes the
  most-recently-used workspace instead of always landing on `default`.
- **B. Make the primary actions obvious** — promote "New plot panel" and "Open JupyterLab"
  to a prominent accent action-row on the welcome page; they are currently lost below the
  Resume hero and a long news list.

The two features share no code beyond living near the startup/welcome surface. They can be
implemented and tested independently.

---

## A. Reopen last workspace on startup

### Today

`resolve_workspace_dir(workspace_name, sciqlop_file)` in `SciQLop/sciqlop_launcher.py` returns
`workspaces_root / "default"` whenever no `--workspace` name and no `.sciqlop` file are passed.
So a bare `sciqlop` launch always opens `default` (the workspace that hosts the welcome page).

Infrastructure already exists:

- `WorkspaceManifest.touch_last_used(dir)` writes a `.last_used` marker; it is called from
  `Workspace.__init__` (`workspace.py:29`), so **every** workspace load — including `default` —
  stamps its marker.
- `WorkspaceManifest.last_used(dir)` returns the marker mtime as an ISO string.
- The welcome page already sorts workspaces by `last_used` for the "Resume" hero
  (`backend.py:get_hero_workspace`).

### Design

Add a boolean setting and consult it in the launcher's workspace resolution.

**Setting** — extend `SciQLopWorkspacesSettings`
(`SciQLop/components/workspaces/backend/settings.py`):

```python
reopen_last_workspace: bool = Field(default=True)
```

`category = WORKSPACES`, `subcategory = "general"` are inherited. The settings UI renders a
`bool` field as a checkbox via the registered bool delegate, and derives the label from the
field name (`field_name.replace('_', ' ').title()` → "Reopen Last Workspace") — no new delegate
and no label hint needed.

**Resolution** — in `resolve_workspace_dir`, after the explicit-name / `.sciqlop`-file branches
and before the `default` fallback:

```python
# explicit --workspace or .sciqlop file always wins (unchanged)
...
if SciQLopWorkspacesSettings().reopen_last_workspace:
    last = _most_recently_used_workspace(workspaces_root)
    if last is not None:
        return last
return workspaces_root / "default"
```

`_most_recently_used_workspace(root)` (new helper, launcher-local):

- Scan immediate subdirectories of `root` that contain a `workspace.sciqlop` manifest.
- Sort by `WorkspaceManifest.last_used(dir)` descending; the marker mtime is the key.
- Return the newest, or `None` if no workspace has a `.last_used` marker (clean first run).

### Behavior / edge cases

| Situation | Result |
|---|---|
| Explicit `--workspace` / `.sciqlop` file | Honored, setting ignored (unchanged) |
| Setting **on**, history exists | Resume newest-used workspace |
| Setting **on**, newest-used **is** `default` | Land on `default` / welcome (same as today) |
| Setting **on**, first run (no markers) | Fall back to `default` |
| Setting **off** | Always `default` (today's behavior) |
| Newest-used workspace dir deleted/corrupt | Skipped (no manifest → not a candidate); next-newest or `default` |

The switch-workspace flow (exit code 65 → `.sciqlop_switch_target`) is unaffected: it passes an
explicit target that takes the explicit branch.

### Why default-on

The welcome page already nudges toward resuming (the "Resume" hero). For a returning user,
landing straight in their last workspace is the expected desktop-app behavior. New users with no
history still get `default` + welcome on first run, so discoverability is preserved.

---

## B. Welcome page — make primary actions obvious

### Today (observed)

Top-to-bottom the welcome page is: filter bar → version strip → **Resume hero** (large, accent,
"Open" button) → **news list (6 dated items)** → `Quick start` (two small cards: JupyterLab,
Plot panel) → Recent workspaces (large thumbnails) → Featured (right column).

The two quickstart cards are "totally lost": the news list pushes them below the fold, and at
their size they read as minor links next to the accent Resume button and the big workspace
thumbnails. The **Plot panel card icon also renders as a blank white square** — a broken icon.

### Design

Three changes, all within the existing palette/visual language (`--Highlight` accent, the hero's
gradient + border treatment):

**1. Primary action-row.** Replace the `#quickstart` small-cards section with a `#primary-actions`
row placed **directly under the version strip, above the Resume hero**. Each action is a large
button: an accent-filled icon tile + bold label + one-line subtitle, using the same
`color-mix(--Highlight …)` gradient and border as `#hero` so it reads as a first-class CTA.

The row stays **data-driven** off the existing quickstart-shortcut registry
(`sciqlop_app().quickstart_shortcuts` → `list_quickstart_shortcuts`). `loadQuickstart()` in
`welcome.js` renders the registered shortcuts into the new `#primary-actions` container with the
CTA markup/classes instead of `.shortcut-card`. Today that is exactly the two desired actions;
any future registered shortcut automatically appears as a CTA. The `run_quickstart(name)` backend
slot is reused unchanged. The old `.shortcut-card` CSS and `#quickstart` section are removed.

**2. Collapse the news banner by default.** The 6-item news list is what buries everything.
Render the banner collapsed to a single summary line (e.g. "📣 N updates — <first titles>…") with
a **"Show all ▾"** toggle that expands the full list; the existing dismiss "×" is kept. Default
state is collapsed. This is presentation-only in `welcome.js` `loadNews()` + a little CSS; the
`list_news` backend is unchanged.

**3. Fix the Plot-panel quickstart icon.** It is registered as
`theme_adapted_icon("plot_panel")` (`mainwindow.py:182`) and serialized to a data-URI via
`_icon_to_data_uri` (renders the QIcon to an 80×80 pixmap). It comes out as a blank square,
whereas JupyterLab's `Icons.get_icon("Jupyter")` renders fine. Fix by sourcing an icon that
survives the detached-pixmap render — mirror the working path (the toolbar's "Add new plot panel"
action uses `theme_icon("add_graph")`, which is a real glyph). Verify the chosen icon produces a
non-empty data-URI before settling.

### CSS

New `.primary-actions` / `.pa` rules in `welcome.css`, derived from the `#hero` block:
accent gradient background, `--Highlight`-tinted border, hover ring
(`box-shadow: 0 0 0 2px color-mix(--Highlight 25% …)`), accent-filled square icon tile. Remove the
`/* Shortcut cards (quickstart) */` block.

### Not in scope

- No change to Recent workspaces / Examples / Templates / Featured layout.
- No new news content source (mock news list stays as-is).
- No reordering beyond placing `#primary-actions` above `#hero`.

---

## Testing

**A. Startup resolution** (`tests/`, pure-function, no Qt):

- `_most_recently_used_workspace`: newest marker wins; ignores dirs without `workspace.sciqlop`;
  returns `None` when no markers.
- `resolve_workspace_dir`: explicit name/file overrides setting; setting-on + history → newest;
  setting-on + no history → `default`; setting-off → `default`. Use a `tmp_path` workspaces root
  and monkeypatch `SciQLopWorkspacesSettings`.

**B. Welcome backend** (extend existing welcome tests):

- `list_quickstart_shortcuts` still returns the registered actions.
- The Plot-panel shortcut's `icon` data-URI is **non-empty** (regression guard for the blank icon).

CSS / visual changes (action-row prominence, news collapse) are verified manually against a
running welcome page; the faithful mockup in `.superpowers/brainstorm/` captures the target.

---

## Files touched (anticipated)

- `SciQLop/components/workspaces/backend/settings.py` — `reopen_last_workspace` field
- `SciQLop/sciqlop_launcher.py` — `_most_recently_used_workspace` + `resolve_workspace_dir`
- `SciQLop/core/ui/mainwindow.py` — Plot-panel quickstart icon
- `SciQLop/components/welcome/resources/welcome.html.j2` — `#primary-actions`, news markup
- `SciQLop/components/welcome/resources/welcome.js` — `loadQuickstart`, `loadNews`
- `SciQLop/components/welcome/resources/welcome.css` — `.primary-actions`/`.pa`, news collapse,
  remove `.shortcut-card`
- `tests/` — startup resolution + welcome icon regression
