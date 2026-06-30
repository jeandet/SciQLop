# Agent Session Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the agent session dropdown with a resizeable, hideable session-list panel that supports renaming and pinning sessions.

**Architecture:** A `ConfigEntry` metadata store (custom name + pinned, keyed by `backend/session_id`) overlays the backend's `list_sessions()`; a pure `ordered_sessions` function applies it and sorts pinned-first; a `SessionListPanel` widget renders it and the chat dock hosts it in a horizontal `QSplitter` (resizeable handle, hideable toggle, persisted width/visibility). In-tree only — no backend protocol or plugin changes.

**Tech Stack:** PySide6 (QListWidget, QSplitter), pydantic settings, pytest + pytest-qt.

## Global Constraints

- Importing any `SciQLop.components.agents.*` module pulls in `ProductsModel` (Qt static) — every test takes the `qtbot` fixture and imports the module inside the test (deferred), matching `tests/test_install_package_tool.py`.
- Metadata key format: `f"{backend}/{session_id}"` where `backend` is the backend's `display_name`. Global store (one YAML).
- Sort order: **pinned first, then `mtime` descending** — `key=lambda d: (not d.pinned, -d.mtime)`.
- A blank custom name falls back to the backend's derived `label`.
- No `delete`, no backend/protocol/plugin change.
- SciQLop test command (repo root, branch `feat/agent-session-panel`): `uv run pytest --no-xvfb <path> -v`. Stage only each task's files — never `git add -A` (untracked build dirs + a modified `uv.lock` exist; do not stage `uv.lock`).

---

## File Structure

- `SciQLop/components/agents/settings.py` — add `SessionMetaEntry`, `AgentSessionMeta`; add two UI-state fields to `AgentChatSettings`.
- `SciQLop/components/agents/chat/sessions_view.py` — new: `DisplaySession`, `ordered_sessions`.
- `SciQLop/components/agents/chat/session_panel.py` — new: `SessionListPanel(QWidget)`.
- `SciQLop/components/agents/chat_dock.py` — replace the dropdown with the panel in a horizontal splitter; toggle + persistence + wiring.
- Tests: `tests/test_session_meta.py`, `tests/test_sessions_view.py`, `tests/test_session_panel.py`.

---

### Task 1: Session metadata store + UI-state settings

**Files:**
- Modify: `SciQLop/components/agents/settings.py`
- Test: `tests/test_session_meta.py`

**Interfaces — Produces:**
- `SessionMetaEntry(BaseModel)`: `name: str = ""`, `pinned: bool = False`.
- `AgentSessionMeta(ConfigEntry)` with `entries: Dict[str, SessionMetaEntry]` and methods `get(backend, session_id) -> SessionMetaEntry`, `set_name(backend, session_id, name)`, `set_pinned(backend, session_id, pinned)`.
- `AgentChatSettings` gains `sessions_pane_visible: bool = True`, `sessions_pane_width: int = 280`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_meta.py`:

```python
"""AgentSessionMeta: name/pin overlay keyed by backend/session_id."""


def _mod(qtbot):
    import SciQLop.components.agents.settings as s
    return s


def test_get_returns_default_for_unknown(qtbot, monkeypatch):
    s = _mod(qtbot)
    monkeypatch.setattr(s.AgentSessionMeta, "save", lambda self: None)
    meta = s.AgentSessionMeta()
    meta.entries = {}
    e = meta.get("Claude", "sess-1")
    assert e.name == "" and e.pinned is False


def test_set_name_and_pin_mutate_and_save(qtbot, monkeypatch):
    s = _mod(qtbot)
    saved = []
    monkeypatch.setattr(s.AgentSessionMeta, "save", lambda self: saved.append(True))
    meta = s.AgentSessionMeta()
    meta.entries = {}
    meta.set_name("Claude", "sess-1", "Magnetopause")
    meta.set_pinned("Claude", "sess-1", True)
    e = meta.get("Claude", "sess-1")
    assert e.name == "Magnetopause" and e.pinned is True
    assert meta.entries["Claude/sess-1"].name == "Magnetopause"
    assert len(saved) == 2  # one save per mutation


def test_settings_have_pane_state_fields(qtbot, monkeypatch):
    s = _mod(qtbot)
    monkeypatch.setattr(s.AgentChatSettings, "save", lambda self: None)
    cfg = s.AgentChatSettings()
    assert cfg.sessions_pane_visible is True
    assert cfg.sessions_pane_width == 280
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_session_meta.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'AgentSessionMeta'` / missing fields.

- [ ] **Step 3: Implement in `settings.py`**

In `SciQLop/components/agents/settings.py`, add to the imports and append the classes; extend `AgentChatSettings`:

```python
from typing import ClassVar, Dict
from pydantic import BaseModel, Field
```
Add the two fields to `AgentChatSettings` (after `tool_verbosity`):
```python
    sessions_pane_visible: bool = Field(default=True, json_schema_extra={"widget": "hidden"})
    sessions_pane_width: int = Field(default=280, json_schema_extra={"widget": "hidden"})
```
Append at module end:
```python
def _session_key(backend: str, session_id: str) -> str:
    return f"{backend}/{session_id}"


class SessionMetaEntry(BaseModel):
    name: str = ""
    pinned: bool = False


class AgentSessionMeta(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Agent chat"
    entries: Dict[str, SessionMetaEntry] = Field(
        default_factory=dict, json_schema_extra={"widget": "hidden"})

    def get(self, backend: str, session_id: str) -> SessionMetaEntry:
        return self.entries.get(_session_key(backend, session_id), SessionMetaEntry())

    def set_name(self, backend: str, session_id: str, name: str) -> None:
        entry = self.entries.setdefault(_session_key(backend, session_id), SessionMetaEntry())
        entry.name = name
        self.save()

    def set_pinned(self, backend: str, session_id: str, pinned: bool) -> None:
        entry = self.entries.setdefault(_session_key(backend, session_id), SessionMetaEntry())
        entry.pinned = pinned
        self.save()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_session_meta.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/settings.py tests/test_session_meta.py
git commit -m "feat(agents): session metadata store (name/pin) + pane-state settings

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Pure ordering overlay

**Files:**
- Create: `SciQLop/components/agents/chat/sessions_view.py`
- Test: `tests/test_sessions_view.py`

**Interfaces:**
- Consumes: `SessionEntry(id, label, mtime)` (from `..backend`); `AgentSessionMeta` (Task 1).
- Produces: `DisplaySession(id, name, pinned, mtime)`; `ordered_sessions(entries, meta, backend) -> list[DisplaySession]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sessions_view.py`:

```python
"""ordered_sessions: name/pin overlay + pinned-first, mtime-desc ordering."""
from dataclasses import dataclass


@dataclass
class _Entry:  # stand-in for SessionEntry
    id: str
    label: str
    mtime: float


class _Meta:  # stand-in for AgentSessionMeta
    def __init__(self, table):
        self._t = table  # {(backend, id): (name, pinned)}

    def get(self, backend, sid):
        from SciQLop.components.agents.settings import SessionMetaEntry
        name, pinned = self._t.get((backend, sid), ("", False))
        return SessionMetaEntry(name=name, pinned=pinned)


def _view(qtbot):
    import SciQLop.components.agents.chat.sessions_view as v
    return v


def test_pinned_first_then_mtime_desc_with_name_override(qtbot):
    v = _view(qtbot)
    entries = [
        _Entry("a", "Auto A", 100.0),
        _Entry("b", "Auto B", 300.0),
        _Entry("c", "Auto C", 200.0),
    ]
    meta = _Meta({("Claude", "a"): ("Pinned-A", True),
                  ("Claude", "c"): ("", True)})
    out = v.ordered_sessions(entries, meta, "Claude")
    assert [d.id for d in out] == ["c", "a", "b"]   # pinned (c mtime>a) first, then b
    assert out[1].name == "Pinned-A"                # custom name applied
    assert out[0].name == "Auto C"                  # blank name -> derived label
    assert out[0].pinned is True and out[2].pinned is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_sessions_view.py -v`
Expected: FAIL — `ModuleNotFoundError: ...chat.sessions_view`.

- [ ] **Step 3: Implement `sessions_view.py`**

Create `SciQLop/components/agents/chat/sessions_view.py`:

```python
"""Overlay backend sessions with custom name + pin metadata, ordered for display."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class DisplaySession:
    id: str
    name: str
    pinned: bool
    mtime: float


def ordered_sessions(entries, meta, backend: str) -> List[DisplaySession]:
    out: List[DisplaySession] = []
    for e in entries:
        m = meta.get(backend, e.id)
        out.append(DisplaySession(
            id=e.id, name=(m.name or e.label), pinned=bool(m.pinned), mtime=e.mtime))
    out.sort(key=lambda d: (not d.pinned, -d.mtime))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_sessions_view.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/chat/sessions_view.py tests/test_sessions_view.py
git commit -m "feat(agents): ordered_sessions overlay (pinned-first, name override)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `SessionListPanel` widget

**Files:**
- Create: `SciQLop/components/agents/chat/session_panel.py`
- Test: `tests/test_session_panel.py`

**Interfaces:**
- Consumes: `DisplaySession` (Task 2).
- Produces: `SessionListPanel(QWidget)` with `set_sessions(list[DisplaySession], current_id=None)` and signals `session_selected(str)`, `rename_requested(str)`, `pin_toggle_requested(str)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_panel.py`:

```python
"""SessionListPanel: rows, pin marker, and activation signal."""
from dataclasses import dataclass


@dataclass
class _DS:
    id: str
    name: str
    pinned: bool
    mtime: float


def _panel(qtbot):
    from SciQLop.components.agents.chat.session_panel import SessionListPanel
    p = SessionListPanel()
    qtbot.addWidget(p)
    return p


def test_set_sessions_builds_rows_with_marker(qtbot):
    p = _panel(qtbot)
    p.set_sessions([_DS("a", "Pinned", True, 2.0), _DS("b", "Plain", False, 1.0)])
    assert p._list.count() == 2
    assert "📌" in p._list.item(0).text() and "Pinned" in p._list.item(0).text()
    assert "📌" not in p._list.item(1).text()
    from PySide6.QtCore import Qt
    assert p._list.item(0).data(Qt.ItemDataRole.UserRole) == "a"


def test_activation_emits_session_selected(qtbot):
    p = _panel(qtbot)
    p.set_sessions([_DS("a", "A", False, 1.0)])
    got = []
    p.session_selected.connect(got.append)
    p._on_activated(p._list.item(0))
    assert got == ["a"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_session_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: ...chat.session_panel`.

- [ ] **Step 3: Implement `session_panel.py`**

Create `SciQLop/components/agents/chat/session_panel.py`:

```python
"""A session-list panel with rename/pin context actions for the agent chat dock."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel, QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QWidget,
)

_ID_ROLE = Qt.ItemDataRole.UserRole
_PIN_ROLE = Qt.ItemDataRole.UserRole + 1


class SessionListPanel(QWidget):
    session_selected = Signal(str)
    rename_requested = Signal(str)
    pin_toggle_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Sessions"))
        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.itemActivated.connect(self._on_activated)
        self._list.itemClicked.connect(self._on_activated)
        self._list.customContextMenuRequested.connect(self._on_menu)
        layout.addWidget(self._list, 1)

    def set_sessions(self, sessions, current_id=None) -> None:
        self._list.clear()
        for s in sessions:
            item = QListWidgetItem(("📌 " if s.pinned else "") + s.name)
            item.setData(_ID_ROLE, s.id)
            item.setData(_PIN_ROLE, bool(s.pinned))
            self._list.addItem(item)
            if current_id is not None and s.id == current_id:
                item.setSelected(True)

    def _on_activated(self, item) -> None:
        sid = item.data(_ID_ROLE) if item is not None else None
        if sid:
            self.session_selected.emit(sid)

    def _on_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        sid = item.data(_ID_ROLE)
        pinned = bool(item.data(_PIN_ROLE))
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.rename_requested.emit(sid))
        menu.addAction("Unpin" if pinned else "Pin",
                       lambda: self.pin_toggle_requested.emit(sid))
        menu.exec(self._list.mapToGlobal(pos))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_session_panel.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/chat/session_panel.py tests/test_session_panel.py
git commit -m "feat(agents): SessionListPanel widget (rename/pin context menu)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire the panel into the chat dock

**Files:**
- Modify: `SciQLop/components/agents/chat_dock.py`

**Interfaces — Consumes:** `AgentSessionMeta`, `AgentChatSettings` (Task 1); `ordered_sessions` (Task 2); `SessionListPanel` (Task 3).

This task is Qt wiring (no new unit test — the testable logic lives in Tasks 1-3, all green). Verify by structural checks + the existing agent suite + a manual smoke.

- [ ] **Step 1: Replace the dropdown with the panel in a horizontal splitter**

In `chat_dock.py` `_build_ui` (around lines 87-91, 121-145): delete the `_session_combo` block (the `QComboBox()`, its tooltip, `currentIndexChanged` connect, and `header.addWidget(self._session_combo)`). Add a checkable toggle button to the header where the combo was:
```python
        self._sessions_toggle = QPushButton("☰ Sessions")
        self._sessions_toggle.setCheckable(True)
        self._sessions_toggle.setToolTip("Show or hide the session list.")
        self._sessions_toggle.toggled.connect(self._on_sessions_toggled)
        header.addWidget(self._sessions_toggle)
```
Add imports at the top: `from PySide6.QtWidgets import QSplitter` (if absent) and:
```python
from SciQLop.components.agents.chat.session_panel import SessionListPanel
from SciQLop.components.agents.chat.sessions_view import ordered_sessions
from SciQLop.components.agents.settings import AgentChatSettings, AgentSessionMeta
```
Wrap the existing vertical `self._splitter` in a horizontal splitter with the panel on the left. Replace `layout.addWidget(self._splitter, 1)` with:
```python
        self._session_panel = SessionListPanel()
        self._session_panel.session_selected.connect(self._on_session_selected)
        self._session_panel.rename_requested.connect(self._on_session_rename)
        self._session_panel.pin_toggle_requested.connect(self._on_session_pin)
        self._h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._h_splitter.addWidget(self._session_panel)
        self._h_splitter.addWidget(self._splitter)
        self._h_splitter.setCollapsible(0, True)
        self._h_splitter.setStretchFactor(1, 1)
        self._h_splitter.splitterMoved.connect(self._on_splitter_moved)
        layout.addWidget(self._h_splitter, 1)
        self._restore_pane_state()
```
(`Qt` is imported in chat_dock; confirm — if not, add `from PySide6.QtCore import Qt`.)

- [ ] **Step 2: Replace `_populate_session_list` to feed the panel**

Replace the body of `_populate_session_list(self, backend)` (was filling `_session_combo`) with:
```python
    def _populate_session_list(self, backend: AgentBackend) -> None:
        self._session_panel.setVisible(
            backend.supports_sessions and self._sessions_toggle.isChecked())
        self._sessions_toggle.setEnabled(backend.supports_sessions)
        if not backend.supports_sessions:
            self._session_panel.set_sessions([])
            return
        session = self._sessions.get(self._current)
        current_id = session.resume_id if session else None
        rows = ordered_sessions(backend.list_sessions(), AgentSessionMeta(),
                                backend.display_name)
        self._session_panel.set_sessions(rows, current_id)
```

- [ ] **Step 3: Add the selection / rename / pin / toggle / persistence handlers**

Add these methods to the dock (replacing the old `_on_session_picked`):
```python
    def _on_session_selected(self, session_id: str) -> None:
        # Mirrors the old _on_session_picked body (minus the combo index lookup).
        if self._current is None:
            return
        session = self._sessions[self._current]
        backend = session.backend
        if not backend.supports_sessions or session_id == session.resume_id:
            return
        session.resume_id = session_id
        self._purge_replay_tempdir(self._current)
        replay_dir = self._tempdir / self._current / "session_replay"
        session.messages = backend.load_session(session_id, replay_dir)
        self._transcript.render_messages(session.messages)
        self._transcript.flush_now()
        self._set_status(
            f"Resumed session {session_id[:8]} ({len(session.messages)} messages)")
        self._spawn(backend.resume(session_id))

    def _on_session_rename(self, session_id: str) -> None:
        session = self._sessions.get(self._current)
        if session is None:
            return
        from PySide6.QtWidgets import QInputDialog
        meta = AgentSessionMeta()
        current = meta.get(session.backend.display_name, session_id).name
        name, ok = QInputDialog.getText(self, "Rename session", "Name:", text=current)
        if ok:
            meta.set_name(session.backend.display_name, session_id, name.strip())
            self._populate_session_list(session.backend)

    def _on_session_pin(self, session_id: str) -> None:
        session = self._sessions.get(self._current)
        if session is None:
            return
        meta = AgentSessionMeta()
        cur = meta.get(session.backend.display_name, session_id).pinned
        meta.set_pinned(session.backend.display_name, session_id, not cur)
        self._populate_session_list(session.backend)

    def _on_sessions_toggled(self, checked: bool) -> None:
        self._session_panel.setVisible(
            checked and self._current_supports_sessions())
        with AgentChatSettings() as cfg:
            cfg.sessions_pane_visible = checked

    def _on_splitter_moved(self, *_args) -> None:
        sizes = self._h_splitter.sizes()
        if sizes and sizes[0] > 0:
            with AgentChatSettings() as cfg:
                cfg.sessions_pane_width = int(sizes[0])

    def _current_supports_sessions(self) -> bool:
        session = self._sessions.get(self._current)
        return bool(session and session.backend.supports_sessions)

    def _restore_pane_state(self) -> None:
        cfg = AgentChatSettings()
        self._sessions_toggle.blockSignals(True)
        self._sessions_toggle.setChecked(cfg.sessions_pane_visible)
        self._sessions_toggle.blockSignals(False)
        width = max(120, int(cfg.sessions_pane_width))
        self._h_splitter.setSizes([width, max(width, 600)])
        self._session_panel.setVisible(cfg.sessions_pane_visible)
```
Notes: delete the old `_on_session_picked` method and any reference to `_session_combo` (e.g. in the tab/focus-order list near line 155). `_on_session_selected` above already mirrors the old resume path exactly (`_purge_replay_tempdir` → `load_session(session_id, replay_dir)` → `_set_status` → `backend.resume`).

- [ ] **Step 4: Verify — no dangling `_session_combo`, parses, existing tests pass**

Run:
```
git grep -n "_session_combo\|_on_session_picked" SciQLop/components/agents/chat_dock.py ; echo "exit:$?"
uv run python -c "import ast; ast.parse(open('SciQLop/components/agents/chat_dock.py').read()); print('parse ok')"
uv run pytest --no-xvfb tests/test_session_meta.py tests/test_sessions_view.py tests/test_session_panel.py tests/test_install_package_tool.py -q
```
Expected: the grep prints nothing and `exit:1` (no leftovers); `parse ok`; tests pass.

- [ ] **Step 5: Manual smoke (record result in the report)**

Launch SciQLop, open the Agents dock: the session panel appears on the left; the splitter handle resizes it; the "☰ Sessions" button hides/shows it; right-click a session → Rename… and Pin/Unpin work; pinned sessions jump to the top with 📌; the width/visibility persist across a dock reopen. Note the outcome.

- [ ] **Step 6: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/chat_dock.py
git commit -m "feat(agents): session list panel in chat dock (rename/pin, resize/hide)

Replaces the session dropdown with a SessionListPanel in a horizontal splitter:
resizeable handle, hideable toggle, pinned-first ordering, rename via dialog,
pane width/visibility persisted.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Metadata store (name/pin, global key, helpers) → Task 1; UI-state persistence fields → Task 1.
- Pure overlay (name override, pinned-first, mtime desc) → Task 2.
- `SessionListPanel` (rows, 📌, context menu, signals) → Task 3.
- Splitter (resize), toggle (hide), persistence, rename dialog, pin, supports_sessions guard, dropdown removal → Task 4. ✓

**Placeholder scan:** none — full code per step. Task 4 Step 3 notes one verify-against-existing point (image tempdir attr name) the implementer confirms from the current `_on_session_picked`.

**Type consistency:** `DisplaySession(id, name, pinned, mtime)` and `ordered_sessions(entries, meta, backend)` are used identically in Tasks 2-4; `AgentSessionMeta.get/set_name/set_pinned(backend, session_id, …)` signatures match between Task 1 and Task 4; `SessionListPanel.set_sessions` + the three signals match Tasks 3-4.
