# Startup & Welcome Quickstart UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resume the last-used workspace on startup (opt-out setting, default on) and make the "New plot panel" / "Open JupyterLab" actions prominent on the welcome page.

**Architecture:** Two independent slices. (A) A boolean on `SciQLopWorkspacesSettings` consulted by the launcher's `resolve_workspace_dir`, which picks the newest `.last_used`-marked workspace via a new pure helper. (B) Welcome-page presentation changes (HTML/CSS/JS) that promote the quickstart shortcuts to an accent action-row, collapse the news banner, and fix the blank Plot-panel icon — driven by the existing quickstart-shortcut registry.

**Tech Stack:** Python 3.14, Pydantic ConfigEntry settings, PySide6/QWebChannel welcome page (Jinja2 + vanilla JS + CSS with Qt-palette CSS variables), pytest.

**Spec:** `docs/superpowers/specs/2026-06-05-startup-and-welcome-quickstart-ux-design.md`

**Run tests with:** `uv run pytest` (always `uv run`).

---

## File Structure

**Feature A — startup resume**
- Modify `SciQLop/components/workspaces/backend/settings.py` — add `reopen_last_workspace` field.
- Modify `SciQLop/sciqlop_launcher.py` — add `_most_recently_used_workspace` helper; consult setting in `resolve_workspace_dir`.
- Modify `tests/test_launcher.py` — helper + resolution tests.

**Feature B — welcome quickstart prominence**
- Modify `SciQLop/core/ui/mainwindow.py:182` — Plot-panel quickstart icon.
- Modify `SciQLop/components/welcome/resources/welcome.html.j2` — `#primary-actions`, news markup.
- Modify `SciQLop/components/welcome/resources/welcome.js` — `loadQuickstart`, `loadNews`.
- Modify `SciQLop/components/welcome/resources/welcome.css` — `.primary-actions`/`.pa`, news collapse, remove `.shortcut-card`.
- Modify `tests/test_welcome_backend.py` (create if absent) — Plot-panel icon renders non-blank.

---

## Task 1: Add `reopen_last_workspace` setting

**Files:**
- Modify: `SciQLop/components/workspaces/backend/settings.py`
- Test: `tests/test_workspaces_settings.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_workspaces_settings.py`:

```python
from SciQLop.components.workspaces.backend.settings import SciQLopWorkspacesSettings


def test_reopen_last_workspace_defaults_true():
    s = SciQLopWorkspacesSettings()
    assert s.reopen_last_workspace is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workspaces_settings.py -v`
Expected: FAIL — `AttributeError` / no field `reopen_last_workspace`.

- [ ] **Step 3: Add the field**

In `SciQLop/components/workspaces/backend/settings.py`, add the field after `workspaces_dir`:

```python
class SciQLopWorkspacesSettings(ConfigEntry):
    category = SettingsCategory.WORKSPACES
    subcategory = "general"
    workspaces_dir: str = Field(default=DEFAULT_WORKSPACE_DIR, json_schema_extra={"widget": "path_dir"})
    reopen_last_workspace: bool = Field(default=True)
```

The settings UI renders `bool` via the registered bool delegate as a checkbox; the label is derived from the field name (`reopen_last_workspace` → "Reopen Last Workspace"). No delegate or hint needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workspaces_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/workspaces/backend/settings.py tests/test_workspaces_settings.py
git commit -m "feat(workspaces): add reopen_last_workspace setting (default on)"
```

---

## Task 2: `_most_recently_used_workspace` launcher helper

Picks the workspace directory with the newest `.last_used` marker. Pure function, no Qt.

**Files:**
- Modify: `SciQLop/sciqlop_launcher.py`
- Test: `tests/test_launcher.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_launcher.py`:

```python
import os
from SciQLop.sciqlop_launcher import _most_recently_used_workspace
from SciQLop.components.workspaces.backend.workspace_manifest import WorkspaceManifest


def _make_ws(root, name, used_mtime):
    d = root / name
    d.mkdir(parents=True)
    (d / "workspace.sciqlop").write_text('[workspace]\nname = "%s"\n' % name)
    WorkspaceManifest.touch_last_used(d)
    os.utime(d / ".last_used", (used_mtime, used_mtime))
    return d


def test_most_recent_picks_newest_marker(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    _make_ws(root, "old", used_mtime=1_000_000)
    newest = _make_ws(root, "fresh", used_mtime=2_000_000)
    assert _most_recently_used_workspace(root) == newest


def test_most_recent_ignores_dirs_without_manifest(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    (root / "not-a-ws").mkdir()  # no workspace.sciqlop
    real = _make_ws(root, "real", used_mtime=1_000_000)
    assert _most_recently_used_workspace(root) == real


def test_most_recent_none_when_no_markers(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    d = root / "ws"
    d.mkdir()
    (d / "workspace.sciqlop").write_text('[workspace]\nname = "ws"\n')  # no .last_used
    assert _most_recently_used_workspace(root) is None


def test_most_recent_none_when_root_missing(tmp_path):
    assert _most_recently_used_workspace(tmp_path / "does-not-exist") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_launcher.py -k most_recent -v`
Expected: FAIL — `ImportError: cannot import name '_most_recently_used_workspace'`.

- [ ] **Step 3: Implement the helper**

In `SciQLop/sciqlop_launcher.py`, add above `resolve_workspace_dir` (after the imports / `parse_args`):

```python
def _most_recently_used_workspace(workspaces_root: Path) -> Path | None:
    """Return the workspace dir with the newest .last_used marker, or None.

    Only directories containing a workspace.sciqlop manifest and a .last_used
    marker are candidates. last_used() returns an ISO timestamp string, which
    sorts chronologically as text.
    """
    from SciQLop.components.workspaces.backend.workspace_manifest import WorkspaceManifest

    if not workspaces_root.is_dir():
        return None
    used = [
        (WorkspaceManifest.last_used(d), d)
        for d in workspaces_root.iterdir()
        if (d / "workspace.sciqlop").is_file()
    ]
    used = [(ts, d) for ts, d in used if ts]
    if not used:
        return None
    used.sort(key=lambda t: t[0], reverse=True)
    return used[0][1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_launcher.py -k most_recent -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/sciqlop_launcher.py tests/test_launcher.py
git commit -m "feat(launcher): add _most_recently_used_workspace helper"
```

---

## Task 3: Consult the setting in `resolve_workspace_dir`

**Files:**
- Modify: `SciQLop/sciqlop_launcher.py` (`resolve_workspace_dir`)
- Test: `tests/test_launcher.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_launcher.py`:

```python
from unittest.mock import MagicMock, patch
from pathlib import Path


def _settings_module(workspaces_dir, reopen):
    inst = MagicMock()
    inst.workspaces_dir = str(workspaces_dir)
    inst.reopen_last_workspace = reopen
    cls = MagicMock(return_value=inst)
    # Only the settings submodule is mocked, so the real WorkspaceManifest
    # is still importable inside the helper.
    return patch.dict("sys.modules", {
        "SciQLop.components.workspaces.backend.settings": MagicMock(
            SciQLopWorkspacesSettings=cls
        ),
    })


def test_resolve_resumes_last_when_enabled(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    _make_ws(root, "old", used_mtime=1_000_000)
    newest = _make_ws(root, "fresh", used_mtime=2_000_000)
    with _settings_module(root, reopen=True):
        d = resolve_workspace_dir(workspace_name=None, sciqlop_file=None)
    assert d == newest


def test_resolve_default_when_reopen_disabled(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    _make_ws(root, "fresh", used_mtime=2_000_000)
    with _settings_module(root, reopen=False):
        d = resolve_workspace_dir(workspace_name=None, sciqlop_file=None)
    assert d == root / "default"


def test_resolve_default_when_no_history(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    with _settings_module(root, reopen=True):
        d = resolve_workspace_dir(workspace_name=None, sciqlop_file=None)
    assert d == root / "default"


def test_resolve_explicit_name_overrides_reopen(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    _make_ws(root, "fresh", used_mtime=2_000_000)
    with _settings_module(root, reopen=True):
        d = resolve_workspace_dir(workspace_name="picked", sciqlop_file=None)
    assert d == root / "picked"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_launcher.py -k "resolve_resumes or reopen_disabled or no_history or overrides_reopen" -v`
Expected: FAIL — `test_resolve_resumes_last_when_enabled` returns `.../default` (helper not wired in yet).

- [ ] **Step 3: Wire the setting into `resolve_workspace_dir`**

In `SciQLop/sciqlop_launcher.py`, replace the final `return workspaces_root / "default"` line of `resolve_workspace_dir` with:

```python
    if getattr(settings, "reopen_last_workspace", True):
        last = _most_recently_used_workspace(workspaces_root)
        if last is not None:
            return last

    return workspaces_root / "default"
```

Leave the `sciqlop_file` and `workspace_name` branches above untouched — explicit targets still win.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_launcher.py -v`
Expected: PASS — new tests pass and the pre-existing `test_resolve_default_workspace` / `test_resolve_named_workspace` / `test_resolve_absolute_path` / file / archive tests still pass (their fake `/fake/workspaces` root does not exist, so the helper returns `None` and they fall back to `default`).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/sciqlop_launcher.py tests/test_launcher.py
git commit -m "feat(launcher): resume last-used workspace on startup when enabled"
```

---

## Task 4: Fix the blank Plot-panel quickstart icon

The Plot-panel shortcut is registered with `theme_adapted_icon("plot_panel")` and renders as a blank white square on the welcome card, whereas the toolbar's "Add new plot panel" action uses `theme_icon("add_graph")` and renders correctly. `WelcomeBackend._icon_to_data_uri` rasterizes the icon to an 80×80 PNG; the goal is a recognizable, non-uniform glyph.

**Files:**
- Modify: `SciQLop/core/ui/mainwindow.py:182`
- Test: `tests/test_welcome_backend.py` (create)

- [ ] **Step 1: Investigate (no code change yet)**

Run a quick probe to confirm the cause and that `theme_icon("add_graph")` rasterizes non-blank:

```bash
uv run python -c "
import SciQLop.resources  # noqa
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
app = QApplication([])
from SciQLop.components.theming import theme_icon, theme_adapted_icon
for name, ic in [('plot_panel(adapted)', theme_adapted_icon('plot_panel')),
                 ('add_graph(theme)', theme_icon('add_graph'))]:
    px = ic.pixmap(QSize(80, 80))
    img = px.toImage()
    colors = {img.pixelColor(x, y).rgba() for x in range(0, 80, 8) for y in range(0, 80, 8)}
    print(name, 'null=', px.isNull(), 'distinct_colors=', len(colors))
"
```
Expected: the chosen replacement (`add_graph(theme)`) reports `distinct_colors > 1`. Use whichever theme glyph passes — `theme_icon("add_graph")` is the proven, semantically-correct choice (same icon as the toolbar action). If for some reason it does not, fall back to `get_icon("add_graph")` / `theme_icon("plot_panel")` and pick the one with `distinct_colors > 1`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_welcome_backend.py`:

```python
from PySide6.QtCore import QSize
from SciQLop.components.welcome.backend import _icon_to_data_uri


def _distinct_colors(icon):
    px = icon.pixmap(QSize(80, 80))
    if px.isNull():
        return 0
    img = px.toImage()
    return len({img.pixelColor(x, y).rgba() for x in range(0, 80, 8) for y in range(0, 80, 8)})


def test_plot_panel_quickstart_icon_renders_non_blank(qapp):
    import SciQLop.resources  # noqa: F401  (registers qrc icons)
    from SciQLop.components.theming import theme_icon
    icon = theme_icon("add_graph")
    assert _distinct_colors(icon) > 1, "plot-panel icon must not be a uniform/blank square"
    uri = _icon_to_data_uri(icon)
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > len("data:image/png;base64,")
```

`qapp` is the pytest-qt fixture (a `QApplication` is required to rasterize icons). If the chosen icon in Step 1 differs from `theme_icon("add_graph")`, use that icon here instead.

- [ ] **Step 3: Run test to verify it fails (or guards the choice)**

Run: `uv run pytest tests/test_welcome_backend.py -v --no-xvfb`
Expected: PASS once the icon choice from Step 1 is correct. (If you deliberately point the test at the broken `theme_adapted_icon("plot_panel")` first, it FAILS on the uniform-color assertion — confirming the regression guard works — then switch it to the chosen icon.)

- [ ] **Step 4: Apply the fix**

In `SciQLop/core/ui/mainwindow.py`, change the Plot-panel quickstart registration (line ~182):

```python
        sciqlop_app().add_quickstart_shortcut(name="Plot panel", description="Add a new plot panel",
                                              icon=theme_icon("add_graph"), callback=self.new_plot_panel)
```

(`theme_icon` is already imported in this module — see the import at line 23.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_welcome_backend.py -v --no-xvfb`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add SciQLop/core/ui/mainwindow.py tests/test_welcome_backend.py
git commit -m "fix(welcome): render the Plot panel quickstart icon (was blank)"
```

---

## Task 5: Welcome HTML — primary-action row + collapsible news markup

**Files:**
- Modify: `SciQLop/components/welcome/resources/welcome.html.j2`

- [ ] **Step 1: Move/rename the quickstart section into a primary-action row above the hero**

In `welcome.html.j2`, locate the `#news-banner` / `#main-content` region. Place a new `#primary-actions` container **between** `#hero` and `#news-banner`, and **remove** the old `#quickstart` section from inside `#left-column`.

Replace this block:

```html
    <div id="hero" class="hidden"></div>

    <div id="news-banner" class="hidden">
        <div id="news-list"></div>
        <button id="news-dismiss" class="news-dismiss" title="Dismiss">&times;</button>
    </div>
```

with:

```html
    <div id="primary-actions"></div>

    <div id="hero" class="hidden"></div>

    <div id="news-banner" class="hidden">
        <div id="news-body">
            <div id="news-summary"></div>
            <div id="news-list" class="collapsed"></div>
            <button id="news-toggle" class="news-toggle" type="button">Show all &#9662;</button>
        </div>
        <button id="news-dismiss" class="news-dismiss" title="Dismiss">&times;</button>
    </div>
```

Then remove the old quickstart section from `#left-column` (the heading + cards row):

```html
            <section id="quickstart">
                <h2>Quick start</h2>
                <div class="cards-row" id="quickstart-cards"></div>
            </section>
```

Leave `#recent-workspaces`, `#examples`, `#templates`, `#featured` unchanged.

- [ ] **Step 2: Sanity-check the template renders**

Run: `uv run pytest -k welcome -v --no-xvfb`
Expected: existing welcome tests (if any) still pass; no template/Jinja error. If there are no welcome rendering tests, skip — the JS/CSS tasks verify behavior at runtime.

- [ ] **Step 3: Commit**

```bash
git add SciQLop/components/welcome/resources/welcome.html.j2
git commit -m "feat(welcome): primary-action row + collapsible news markup"
```

---

## Task 6: Welcome CSS — action-row styling, news collapse, drop shortcut-card

**Files:**
- Modify: `SciQLop/components/welcome/resources/welcome.css`

- [ ] **Step 1: Add `.primary-actions` / `.pa` rules**

Insert after the `#hero` block (i.e. before `/* --- News banner --- */`):

```css
/* --- Primary action row --- */

#primary-actions {
    display: flex;
    gap: 14px;
    margin-bottom: 18px;
}

#primary-actions:empty {
    display: none;
}

.pa {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 16px 20px;
    border-radius: 10px;
    cursor: pointer;
    background: linear-gradient(135deg,
        color-mix(in srgb, var(--Highlight) 22%, var(--Window)),
        color-mix(in srgb, var(--Highlight) 8%, var(--Window)));
    border: 1px solid color-mix(in srgb, var(--Highlight) 45%, var(--Borders));
    transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s ease;
}

.pa:hover {
    border-color: var(--Highlight);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--Highlight) 25%, transparent);
    transform: translateY(-1px);
}

.pa .pa-icon {
    width: 44px;
    height: 44px;
    border-radius: 8px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--Highlight);
}

.pa .pa-icon img {
    width: 28px;
    height: 28px;
}

.pa .pa-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
}

.pa .pa-name {
    font-weight: 600;
    font-size: 1.05em;
}

.pa .pa-desc {
    font-size: 0.85em;
    color: var(--UnselectedText);
}
```

- [ ] **Step 2: Add news collapse rules**

In the `/* --- News banner --- */` section, after `#news-banner #news-list { ... }`, add:

```css
#news-banner #news-body {
    flex: 1;
    min-width: 0;
}

#news-summary {
    font-size: 0.9em;
    color: var(--Text);
}

#news-list.collapsed {
    display: none;
}

.news-toggle {
    background: none;
    border: none;
    color: var(--Highlight);
    cursor: pointer;
    font-size: 0.85em;
    padding: 4px 0 0;
}

.news-toggle:hover {
    text-decoration: underline;
}
```

- [ ] **Step 3: Remove the obsolete `.shortcut-card` block**

Delete the entire block starting at `/* --- Shortcut cards (quickstart) --- */` up to (but not including) `/* --- New workspace card --- */` (the `.shortcut-card`, `.shortcut-card:hover`, `.shortcut-card .shortcut-name`, `.shortcut-card .shortcut-desc` rules).

- [ ] **Step 4: Commit**

```bash
git add SciQLop/components/welcome/resources/welcome.css
git commit -m "feat(welcome): accent action-row + news-collapse styling"
```

---

## Task 7: Welcome JS — render action-row + collapse news

**Files:**
- Modify: `SciQLop/components/welcome/resources/welcome.js`

- [ ] **Step 1: Rewrite `loadQuickstart` to render the action-row**

Replace the entire `loadQuickstart` function (currently rendering `.shortcut-card`s into `#quickstart-cards`) with:

```javascript
function loadQuickstart() {
    backend.list_quickstart_shortcuts(function(json_str) {
        const shortcuts = JSON.parse(json_str);
        const container = document.getElementById("primary-actions");
        container.innerHTML = "";
        shortcuts.forEach(function(s) {
            const action = document.createElement("div");
            action.className = "pa";

            const iconWrap = document.createElement("div");
            iconWrap.className = "pa-icon";
            if (s.icon) {
                const img = document.createElement("img");
                img.src = s.icon;
                iconWrap.appendChild(img);
            }
            action.appendChild(iconWrap);

            const text = document.createElement("div");
            text.className = "pa-text";
            const name = document.createElement("span");
            name.className = "pa-name";
            name.textContent = s.name;
            text.appendChild(name);
            if (s.description) {
                const desc = document.createElement("span");
                desc.className = "pa-desc";
                desc.textContent = s.description;
                text.appendChild(desc);
            }
            action.appendChild(text);

            action.addEventListener("click", function() {
                backend.run_quickstart(s.name);
            });
            container.appendChild(action);
        });
    });
}
```

- [ ] **Step 2: Update the quickstart filter block**

In `applyGlobalFilter` (around `welcome.js:647`), replace this exact block:

```javascript
    // Also filter quickstart shortcuts
    var qsContainer = document.getElementById("quickstart-cards");
    if (qsContainer) {
        var shortcuts = qsContainer.querySelectorAll(".shortcut-card");
        shortcuts.forEach(function(card) {
            var name = (card.querySelector(".shortcut-name") || {}).textContent || "";
            var match = !filtering || name.toLowerCase().includes(query);
            card.style.display = match ? "" : "none";
        });
    }
```

with:

```javascript
    // Also filter quickstart shortcuts
    var qsContainer = document.getElementById("primary-actions");
    if (qsContainer) {
        var shortcuts = qsContainer.querySelectorAll(".pa");
        shortcuts.forEach(function(card) {
            var name = (card.querySelector(".pa-name") || {}).textContent || "";
            var match = !filtering || name.toLowerCase().includes(query);
            card.style.display = match ? "" : "none";
        });
    }
```

- [ ] **Step 3: Rewrite `loadNews` to collapse by default with a toggle**

Replace the entire `loadNews` function with:

```javascript
function loadNews() {
    backend.list_news(function(json_str) {
        const news = JSON.parse(json_str);
        const banner = document.getElementById("news-banner");
        const list = document.getElementById("news-list");
        const summary = document.getElementById("news-summary");
        const toggle = document.getElementById("news-toggle");
        list.innerHTML = "";
        if (!news || news.length === 0) {
            banner.classList.add("hidden");
            return;
        }
        summary.textContent = "📣 " + news.length +
            (news.length === 1 ? " update" : " updates");
        news.forEach(function(item) {
            const row = document.createElement("div");
            row.className = "news-item";
            row.innerHTML =
                '<span class="news-icon">' + item.icon + '</span>' +
                '<span class="news-text">' + escapeHtml(item.title) + '</span>' +
                '<span class="news-date">' + escapeHtml(item.date || "") + '</span>';
            list.appendChild(row);
        });
        list.classList.add("collapsed");
        toggle.textContent = "Show all ▾";
        toggle.onclick = function() {
            const collapsed = list.classList.toggle("collapsed");
            toggle.textContent = collapsed ? "Show all ▾" : "Show less ▴";
        };
        banner.classList.remove("hidden");
        document.getElementById("news-dismiss").addEventListener("click", function() {
            banner.classList.add("hidden");
        });
    });
}
```

- [ ] **Step 4: Manual verification in the running app**

Run: `uv run sciqlop`
Verify on the Welcome tab:
1. Two large accent action buttons ("Open JupyterLab", "Plot panel") sit directly under the version strip, above the Resume hero.
2. The Plot-panel button shows a real icon (not a blank white square); clicking it adds a plot panel; clicking JupyterLab opens it.
3. The news banner shows a single summary line ("📣 7 updates") with a "Show all ▾" toggle that expands/collapses the list; the × still dismisses it.
4. The old small "Quick start" cards section is gone.
5. Typing in the filter still narrows the action buttons (no JS console error).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/welcome/resources/welcome.js
git commit -m "feat(welcome): render primary-action row and collapse news by default"
```

---

## Self-review notes

- **Spec coverage:** A.setting → Task 1; A.resolution + edge cases → Tasks 2–3; B.action-row → Tasks 5–7; B.news-collapse → Tasks 5–7; B.icon-fix → Task 4; remove old quickstart cards → Tasks 5 (HTML), 6 (CSS), 7 (JS). All spec sections covered.
- **Name consistency:** container `#primary-actions`, item class `.pa`, sub-classes `.pa-icon`/`.pa-text`/`.pa-name`/`.pa-desc`; news ids `#news-summary`/`#news-list`/`#news-toggle`/`#news-dismiss` — used identically across HTML (Task 5), CSS (Task 6) and JS (Task 7).
- **Backend reuse:** `list_quickstart_shortcuts` / `run_quickstart` are unchanged; the action-row is data-driven off the existing registry. No backend signature changes.
- **Regression safety:** existing `tests/test_launcher.py` resolution tests rely on a non-existent `/fake/workspaces` root, so the new resume branch returns `None` and they still resolve to `default`.
