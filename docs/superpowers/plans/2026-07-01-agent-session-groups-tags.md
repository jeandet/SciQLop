# Agent Session Groups & Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add folders (flat groups), tags, and a name/tag filter to the agent session panel, with drag-and-drop moves, group rename/delete, and tag autocomplete.

**Architecture:** `SessionMetaEntry` gains `group`/`tags`; a pure `grouped_sessions` builds an ordered list of `SessionGroup`s (📌 Pinned first, groups alpha, Ungrouped last); the `SessionListPanel` becomes a `QTreeWidget` with a filter box and drag-drop; `chat_dock` wires filter/move/tags/group dialogs. In-tree only.

**Tech Stack:** PySide6 (QTreeWidget, QCompleter), pydantic settings, pytest + pytest-qt.

## Global Constraints

- Importing any `SciQLop.components.agents.*` module needs a QApplication — every test takes the `qtbot` fixture and imports the module inside the test (deferred), matching `tests/test_session_panel.py`.
- One group per session, many tags. Metadata key `f"{backend}/{session_id}"` (backend = `display_name`), unchanged.
- Group order: synthetic `"📌 Pinned"` (constant `PINNED_GROUP`) first iff any pinned; then real groups sorted by name; then `"Ungrouped"` (constant `UNGROUPED`) last iff any. Within a group: `mtime` descending. Empty groups omitted.
- Filter: case-insensitive substring of the display name OR any tag; blank = all.
- Blank group = Ungrouped; `delete_group` == `rename_group(..., "")`; sessions are never deleted.
- In-session expand/collapse preservation only (track collapsed group names in memory); no cross-restart persistence.
- SciQLop test command (repo root, branch `feat/agent-session-groups`): `uv run pytest --no-xvfb <path> -v`. Stage only each task's files — never `git add -A` (untracked build dirs + modified `uv.lock`; do not stage `uv.lock`).

---

## File Structure

- `SciQLop/components/agents/settings.py` — `SessionMetaEntry` (+group/tags); `AgentSessionMeta` (+set_group/set_tags/rename_group/delete_group).
- `SciQLop/components/agents/chat/sessions_view.py` — `DisplaySession` (+group/tags), `SessionGroup`, `grouped_sessions`, `all_tags`, `all_groups`, constants; `ordered_sessions` removed in Task 4.
- `SciQLop/components/agents/chat/session_panel.py` — `QListWidget` → `QTreeWidget` rewrite.
- `SciQLop/components/agents/chat_dock.py` — grouped feed + filter/move/tags/group handlers (Task 4).
- Tests: `tests/test_session_meta_groups.py`, `tests/test_sessions_view_groups.py`, `tests/test_session_panel.py` (rewrite).

---

### Task 1: Group/tag metadata

**Files:**
- Modify: `SciQLop/components/agents/settings.py`
- Test: `tests/test_session_meta_groups.py` (create)

**Interfaces — Produces:** `SessionMetaEntry` fields `group: str`, `tags: List[str]`; `AgentSessionMeta.set_group(backend, id, group)`, `.set_tags(backend, id, tags)`, `.rename_group(backend, old, new)`, `.delete_group(backend, group)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_meta_groups.py`:

```python
"""AgentSessionMeta group/tag helpers."""


def _mod(qtbot):
    import SciQLop.components.agents.settings as s
    return s


def _meta(s, monkeypatch):
    monkeypatch.setattr(s.AgentSessionMeta, "save", lambda self: None)
    m = s.AgentSessionMeta()
    m.entries = {}
    return m


def test_set_group_and_tags(qtbot, monkeypatch):
    s = _mod(qtbot)
    m = _meta(s, monkeypatch)
    m.set_group("Claude", "a", "MMS")
    m.set_tags("Claude", "a", ["recon", "dayside"])
    e = m.get("Claude", "a")
    assert e.group == "MMS" and e.tags == ["recon", "dayside"]


def test_rename_group_moves_all_members(qtbot, monkeypatch):
    s = _mod(qtbot)
    m = _meta(s, monkeypatch)
    m.set_group("Claude", "a", "MMS")
    m.set_group("Claude", "b", "MMS")
    m.set_group("Claude", "c", "SW")
    m.set_group("Opencode", "a", "MMS")  # different backend, must not move
    m.rename_group("Claude", "MMS", "Magnetotail")
    assert m.get("Claude", "a").group == "Magnetotail"
    assert m.get("Claude", "b").group == "Magnetotail"
    assert m.get("Claude", "c").group == "SW"
    assert m.get("Opencode", "a").group == "MMS"


def test_delete_group_ungroups_members(qtbot, monkeypatch):
    s = _mod(qtbot)
    m = _meta(s, monkeypatch)
    m.set_group("Claude", "a", "MMS")
    m.set_group("Claude", "b", "MMS")
    m.delete_group("Claude", "MMS")
    assert m.get("Claude", "a").group == "" and m.get("Claude", "b").group == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_session_meta_groups.py -v`
Expected: FAIL — `AttributeError: 'SessionMetaEntry' object has no attribute 'group'` / no `set_group`.

- [ ] **Step 3: Implement in `settings.py`**

Ensure `List` is imported: change `from typing import ClassVar, Dict` to `from typing import ClassVar, Dict, List`.
Extend `SessionMetaEntry`:
```python
class SessionMetaEntry(BaseModel):
    name: str = ""
    pinned: bool = False
    group: str = ""
    tags: List[str] = Field(default_factory=list)
```
Add to `AgentSessionMeta` (after `set_pinned`):
```python
    def set_group(self, backend: str, session_id: str, group: str) -> None:
        entry = self.entries.setdefault(_session_key(backend, session_id), SessionMetaEntry())
        entry.group = group
        self.save()

    def set_tags(self, backend: str, session_id: str, tags: List[str]) -> None:
        entry = self.entries.setdefault(_session_key(backend, session_id), SessionMetaEntry())
        entry.tags = list(tags)
        self.save()

    def rename_group(self, backend: str, old: str, new: str) -> None:
        prefix = f"{backend}/"
        changed = False
        for key, entry in self.entries.items():
            if key.startswith(prefix) and entry.group == old:
                entry.group = new
                changed = True
        if changed:
            self.save()

    def delete_group(self, backend: str, group: str) -> None:
        self.rename_group(backend, group, "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_session_meta_groups.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/settings.py tests/test_session_meta_groups.py
git commit -m "feat(agents): session group/tag metadata (set_group/tags, rename/delete group)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Grouped view model

**Files:**
- Modify: `SciQLop/components/agents/chat/sessions_view.py`
- Test: `tests/test_sessions_view_groups.py` (create)

**Interfaces:**
- Consumes: `SessionMetaEntry` (group/tags), `SessionEntry(id,label,mtime)`.
- Produces: `DisplaySession(id,name,pinned,mtime,group,tags)`; `SessionGroup(name, sessions)`; `PINNED_GROUP`, `UNGROUPED`; `grouped_sessions(entries, meta, backend, filter_text="") -> list[SessionGroup]`; `all_tags(entries, meta, backend) -> list[str]`; `all_groups(entries, meta, backend) -> list[str]`.

**Note:** keep the existing `ordered_sessions` untouched (Task 4 removes it after `chat_dock` switches over) so `chat_dock` keeps importing it in the meantime.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sessions_view_groups.py`:

```python
"""grouped_sessions / all_tags / all_groups."""
from dataclasses import dataclass


@dataclass
class _Entry:
    id: str
    label: str
    mtime: float


class _Meta:
    def __init__(self, table):
        self._t = table  # {(backend, id): (name, pinned, group, tags)}

    def get(self, backend, sid):
        from SciQLop.components.agents.settings import SessionMetaEntry
        name, pinned, group, tags = self._t.get((backend, sid), ("", False, "", []))
        return SessionMetaEntry(name=name, pinned=pinned, group=group, tags=list(tags))


def _view(qtbot):
    import SciQLop.components.agents.chat.sessions_view as v
    return v


def _entries():
    return [_Entry("a", "Auto A", 100.0), _Entry("b", "Auto B", 300.0),
            _Entry("c", "Auto C", 200.0), _Entry("d", "Auto D", 400.0)]


def test_group_order_and_within_group_sort(qtbot):
    v = _view(qtbot)
    meta = _Meta({
        ("K", "a"): ("", True, "MMS", ["recon"]),     # pinned + in MMS
        ("K", "b"): ("", False, "MMS", []),           # MMS
        ("K", "c"): ("", False, "SW", []),            # SW
        ("K", "d"): ("", False, "", []),              # ungrouped
    })
    groups = v.grouped_sessions(_entries(), meta, "K")
    assert [g.name for g in groups] == [v.PINNED_GROUP, "MMS", "SW", v.UNGROUPED]
    assert [s.id for s in groups[0].sessions] == ["a"]          # pinned
    assert [s.id for s in groups[1].sessions] == ["b", "a"]     # MMS: b(300) before a(100)
    assert [s.id for s in groups[3].sessions] == ["d"]


def test_filter_matches_name_and_tags(qtbot):
    v = _view(qtbot)
    meta = _Meta({
        ("K", "a"): ("Magnetopause", False, "MMS", ["dayside"]),
        ("K", "b"): ("Turbulence", False, "SW", ["solarwind"]),
    })
    entries = [_Entry("a", "x", 1.0), _Entry("b", "y", 2.0)]
    by_name = v.grouped_sessions(entries, meta, "K", "magneto")
    assert [s.id for g in by_name for s in g.sessions] == ["a"]
    by_tag = v.grouped_sessions(entries, meta, "K", "solarwind")
    assert [s.id for g in by_tag for s in g.sessions] == ["b"]
    assert v.grouped_sessions(entries, meta, "K", "zzz") == []


def test_all_tags_and_groups_sorted_unique(qtbot):
    v = _view(qtbot)
    meta = _Meta({
        ("K", "a"): ("", False, "MMS", ["b", "a"]),
        ("K", "b"): ("", False, "SW", ["a", "c"]),
        ("K", "c"): ("", False, "", []),
    })
    entries = [_Entry("a", "", 1.0), _Entry("b", "", 2.0), _Entry("c", "", 3.0)]
    assert v.all_tags(entries, meta, "K") == ["a", "b", "c"]
    assert v.all_groups(entries, meta, "K") == ["MMS", "SW"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_sessions_view_groups.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'grouped_sessions'`.

- [ ] **Step 3: Extend `sessions_view.py`**

Change the `DisplaySession` dataclass to add fields, and append the new code. `DisplaySession`:
```python
from dataclasses import dataclass, field
from typing import List


@dataclass
class DisplaySession:
    id: str
    name: str
    pinned: bool
    mtime: float
    group: str = ""
    tags: List[str] = field(default_factory=list)
```
Append at the end of the module:
```python
PINNED_GROUP = "📌 Pinned"
UNGROUPED = "Ungrouped"


@dataclass
class SessionGroup:
    name: str
    sessions: List[DisplaySession]


def _display_sessions(entries, meta, backend: str) -> List[DisplaySession]:
    out = []
    for e in entries:
        m = meta.get(backend, e.id)
        out.append(DisplaySession(
            id=e.id, name=(m.name or e.label), pinned=bool(m.pinned),
            mtime=e.mtime, group=m.group, tags=list(m.tags)))
    return out


def _matches(d: DisplaySession, needle: str) -> bool:
    if not needle:
        return True
    n = needle.lower()
    return n in d.name.lower() or any(n in t.lower() for t in d.tags)


def grouped_sessions(entries, meta, backend: str, filter_text: str = "") -> List[SessionGroup]:
    items = [d for d in _display_sessions(entries, meta, backend) if _matches(d, filter_text)]
    by_mtime = lambda d: -d.mtime
    groups: List[SessionGroup] = []
    pinned = sorted([d for d in items if d.pinned], key=by_mtime)
    if pinned:
        groups.append(SessionGroup(PINNED_GROUP, pinned))
    named: dict = {}
    for d in items:
        if d.group:
            named.setdefault(d.group, []).append(d)
    for name in sorted(named):
        groups.append(SessionGroup(name, sorted(named[name], key=by_mtime)))
    ungrouped = sorted([d for d in items if not d.group], key=by_mtime)
    if ungrouped:
        groups.append(SessionGroup(UNGROUPED, ungrouped))
    return groups


def all_tags(entries, meta, backend: str) -> List[str]:
    tags = set()
    for e in entries:
        tags.update(meta.get(backend, e.id).tags)
    return sorted(tags)


def all_groups(entries, meta, backend: str) -> List[str]:
    groups = set()
    for e in entries:
        g = meta.get(backend, e.id).group
        if g:
            groups.add(g)
    return sorted(groups)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_sessions_view_groups.py tests/test_sessions_view.py -v`
Expected: PASS (the new 3 + the retained `ordered_sessions` test).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/chat/sessions_view.py tests/test_sessions_view_groups.py
git commit -m "feat(agents): grouped_sessions view model + all_tags/all_groups

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Tree panel with filter, drag-drop, group menus

**Files:**
- Rewrite: `SciQLop/components/agents/chat/session_panel.py`
- Test: `tests/test_session_panel.py` (rewrite)

**Interfaces:**
- Consumes: `SessionGroup`/`DisplaySession`, `PINNED_GROUP`/`UNGROUPED` (Task 2).
- Produces: `SessionListPanel(QWidget)` — `set_groups(groups, current_id=None)`; signals `session_selected(str)`, `rename_requested(str)`, `pin_toggle_requested(str)`, `move_requested(str)`, `tags_edit_requested(str)`, `session_moved(str, str)`, `group_rename_requested(str)`, `group_delete_requested(str)`, `filter_changed(str)`; module function `_resolve_drop_group(item) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_session_panel.py`:

```python
"""SessionListPanel tree: rows, filter, context menus, drop resolution."""
from dataclasses import dataclass, field


@dataclass
class _DS:
    id: str
    name: str
    pinned: bool
    mtime: float
    group: str = ""
    tags: list = field(default_factory=list)


def _panel(qtbot):
    from SciQLop.components.agents.chat.session_panel import SessionListPanel
    p = SessionListPanel()
    qtbot.addWidget(p)
    return p


def _groups():
    from SciQLop.components.agents.chat.sessions_view import SessionGroup, PINNED_GROUP, UNGROUPED
    return [
        SessionGroup(PINNED_GROUP, [_DS("a", "Pinned one", True, 2.0)]),
        SessionGroup("MMS", [_DS("a", "Pinned one", True, 2.0), _DS("b", "Plain", False, 1.0)]),
        SessionGroup(UNGROUPED, [_DS("c", "Loose", False, 0.5)]),
    ]


def test_set_groups_builds_tree(qtbot):
    p = _panel(qtbot)
    p.set_groups(_groups())
    tree = p._tree
    assert tree.topLevelItemCount() == 3
    assert tree.topLevelItem(0).text(0).startswith("📌 Pinned (1)")
    assert tree.topLevelItem(1).text(0) == "MMS (2)"
    # pinned child carries the marker + id role
    from PySide6.QtCore import Qt
    child = tree.topLevelItem(1).child(0)
    assert "📌" in child.text(0)
    assert child.data(0, Qt.ItemDataRole.UserRole) == "a"


def test_activation_emits_only_for_sessions(qtbot):
    p = _panel(qtbot)
    p.set_groups(_groups())
    got = []
    p.session_selected.connect(got.append)
    p._on_activated(p._tree.topLevelItem(1).child(1))  # a session
    p._on_activated(p._tree.topLevelItem(1))           # a header -> no emit
    assert got == ["b"]


def test_filter_box_emits(qtbot):
    p = _panel(qtbot)
    seen = []
    p.filter_changed.connect(seen.append)
    p._filter.setText("mms")
    assert seen[-1] == "mms"


def test_expand_state_preserved_across_rebuild(qtbot):
    p = _panel(qtbot)
    p.set_groups(_groups())
    p._on_collapsed(p._tree.topLevelItem(1))  # user collapsed MMS -> recorded
    p.set_groups(_groups())                   # rebuild
    assert p._tree.topLevelItem(1).isExpanded() is False


def test_resolve_drop_group(qtbot):
    import SciQLop.components.agents.chat.session_panel as sp
    from SciQLop.components.agents.chat.sessions_view import PINNED_GROUP, UNGROUPED
    p = _panel(qtbot)
    p.set_groups(_groups())
    pinned_hdr, mms_hdr, ungrouped_hdr = (p._tree.topLevelItem(i) for i in range(3))
    assert sp._resolve_drop_group(mms_hdr) == "MMS"          # onto a real group
    assert sp._resolve_drop_group(mms_hdr.child(1)) == "MMS"  # onto a session -> its group
    assert sp._resolve_drop_group(ungrouped_hdr) == ""        # onto Ungrouped
    assert sp._resolve_drop_group(None) == ""                 # empty area
    assert sp._resolve_drop_group(pinned_hdr) is None         # Pinned rejects


def test_group_header_menu_signals(qtbot):
    p = _panel(qtbot)
    p.set_groups(_groups())
    renamed, deleted = [], []
    p.group_rename_requested.connect(renamed.append)
    p.group_delete_requested.connect(deleted.append)
    # emulate the actions the header context menu wires
    p._emit_group_rename(p._tree.topLevelItem(1))
    p._emit_group_delete(p._tree.topLevelItem(1))
    assert renamed == ["MMS"] and deleted == ["MMS"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_session_panel.py -v`
Expected: FAIL — new API (`_tree`, `set_groups`, `_resolve_drop_group`, `_emit_group_*`) not present.

- [ ] **Step 3: Rewrite `session_panel.py`**

```python
"""Grouped, filterable session-list panel with drag-drop and rename/pin/tag actions."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .sessions_view import PINNED_GROUP, UNGROUPED

_ID_ROLE = Qt.ItemDataRole.UserRole          # session id (session items)
_PIN_ROLE = Qt.ItemDataRole.UserRole + 1     # bool pinned (session items)
_GROUP_ROLE = Qt.ItemDataRole.UserRole + 2   # raw group name (header items; "" for ungrouped)
_KIND_ROLE = Qt.ItemDataRole.UserRole + 3    # "pinned" | "group" | "ungrouped" (header items)


def _resolve_drop_group(item):
    """Target group for a drop onto `item`: real group name, "" for ungrouped,
    or None to reject (the synthetic Pinned group)."""
    if item is None:
        return ""  # empty area -> ungrouped
    header = item if item.parent() is None else item.parent()
    kind = header.data(0, _KIND_ROLE)
    if kind == "pinned":
        return None
    if kind == "ungrouped":
        return ""
    return header.data(0, _GROUP_ROLE)


class _SessionTree(QTreeWidget):
    dropped = Signal(str, str)  # session_id, target_group ("" = ungrouped)

    def dropEvent(self, event):  # noqa: N802 (Qt override)
        source = self.currentItem()
        if source is None or source.parent() is None:
            event.ignore()
            return
        sid = source.data(0, _ID_ROLE)
        group = _resolve_drop_group(self.itemAt(event.position().toPoint()))
        if sid and group is not None:
            self.dropped.emit(sid, group)
        event.ignore()  # never let Qt move items — the tree is rebuilt from data


class SessionListPanel(QWidget):
    session_selected = Signal(str)
    rename_requested = Signal(str)
    pin_toggle_requested = Signal(str)
    move_requested = Signal(str)
    tags_edit_requested = Signal(str)
    session_moved = Signal(str, str)
    group_rename_requested = Signal(str)
    group_delete_requested = Signal(str)
    filter_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed: set[str] = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Sessions"))
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("filter name or tag…")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self.filter_changed)
        layout.addWidget(self._filter)
        self._tree = _SessionTree()
        self._tree.setHeaderHidden(True)
        self._tree.setDragDropMode(QTreeWidget.DragDropMode.DragDrop)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.itemActivated.connect(lambda it, _c=0: self._on_activated(it))
        self._tree.itemClicked.connect(lambda it, _c=0: self._on_activated(it))
        self._tree.customContextMenuRequested.connect(self._on_menu)
        self._tree.itemCollapsed.connect(self._on_collapsed)
        self._tree.itemExpanded.connect(self._on_expanded)
        self._tree.dropped.connect(self.session_moved)
        layout.addWidget(self._tree, 1)

    def set_groups(self, groups, current_id=None) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        for g in groups:
            kind = ("pinned" if g.name == PINNED_GROUP
                    else "ungrouped" if g.name == UNGROUPED else "group")
            header = QTreeWidgetItem(self._tree, [f"{g.name} ({len(g.sessions)})"])
            header.setData(0, _KIND_ROLE, kind)
            header.setData(0, _GROUP_ROLE, g.name if kind == "group" else "")
            header.setFlags((header.flags() & ~Qt.ItemFlag.ItemIsDragEnabled
                             & ~Qt.ItemFlag.ItemIsSelectable) | Qt.ItemFlag.ItemIsDropEnabled)
            for s in g.sessions:
                child = QTreeWidgetItem(header, [("📌 " if s.pinned else "") + s.name])
                child.setData(0, _ID_ROLE, s.id)
                child.setData(0, _PIN_ROLE, bool(s.pinned))
                child.setFlags((child.flags() | Qt.ItemFlag.ItemIsDragEnabled)
                               & ~Qt.ItemFlag.ItemIsDropEnabled)
                if current_id is not None and s.id == current_id:
                    child.setSelected(True)
            header.setExpanded(g.name not in self._collapsed)
        self._tree.blockSignals(False)

    def _on_activated(self, item) -> None:
        if item is not None and item.parent() is not None:
            sid = item.data(0, _ID_ROLE)
            if sid:
                self.session_selected.emit(sid)

    def _on_collapsed(self, item) -> None:
        if item.parent() is None:
            self._collapsed.add(item.data(0, _GROUP_ROLE) or item.text(0))

    def _on_expanded(self, item) -> None:
        if item.parent() is None:
            self._collapsed.discard(item.data(0, _GROUP_ROLE) or item.text(0))

    def _emit_group_rename(self, header) -> None:
        self.group_rename_requested.emit(header.data(0, _GROUP_ROLE))

    def _emit_group_delete(self, header) -> None:
        self.group_delete_requested.emit(header.data(0, _GROUP_ROLE))

    def _on_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        if item.parent() is None:
            if item.data(0, _KIND_ROLE) != "group":
                return  # no menu for Pinned / Ungrouped headers
            menu.addAction("Rename group…", lambda: self._emit_group_rename(item))
            menu.addAction("Delete group", lambda: self._emit_group_delete(item))
        else:
            sid = item.data(0, _ID_ROLE)
            pinned = bool(item.data(0, _PIN_ROLE))
            menu.addAction("Rename…", lambda: self.rename_requested.emit(sid))
            menu.addAction("Unpin" if pinned else "Pin",
                           lambda: self.pin_toggle_requested.emit(sid))
            menu.addAction("Move to group…", lambda: self.move_requested.emit(sid))
            menu.addAction("Edit tags…", lambda: self.tags_edit_requested.emit(sid))
        menu.exec(self._tree.mapToGlobal(pos))
```

Note on the collapse-key: headers store their group name in `_GROUP_ROLE` for real groups (""), so for Pinned/Ungrouped the fallback `item.text(0)` (which includes the count) is used as the collapse key — that is fine because those two headers are singletons whose text is stable enough for in-session preservation; real groups key off the stable raw name.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_session_panel.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/chat/session_panel.py tests/test_session_panel.py
git commit -m "feat(agents): grouped session tree panel (filter, drag-drop, group menus)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire groups/tags into the chat dock

**Files:**
- Modify: `SciQLop/components/agents/chat_dock.py`
- Modify: `SciQLop/components/agents/chat/sessions_view.py` (remove dead `ordered_sessions`)
- Modify: `tests/test_sessions_view.py` (drop the removed `ordered_sessions` test)

This is Qt wiring; the risky logic is unit-tested in Tasks 1-3. Verify structurally + existing suites + a manual smoke.

- [ ] **Step 1: Switch `_populate_session_list` to grouped feed**

In `chat_dock.py`: change the import
```python
from .chat.sessions_view import ordered_sessions
```
to
```python
from .chat.sessions_view import grouped_sessions, all_groups, all_tags
```
Add `self._session_filter = ""` in `__init__` (near the other instance attrs). Replace the body that built `rows = ordered_sessions(...)` / `self._session_panel.set_sessions(rows, current_id)` with:
```python
        groups = grouped_sessions(backend.list_sessions(), AgentSessionMeta(),
                                  backend.display_name, self._session_filter)
        self._session_panel.set_groups(groups, current_id)
```
(keep the surrounding `supports_sessions` visibility/enable guards unchanged).

- [ ] **Step 2: Connect the new panel signals**

Where the panel signals are connected (next to `session_selected`/`rename_requested`/`pin_toggle_requested`), add:
```python
        self._session_panel.filter_changed.connect(self._on_session_filter)
        self._session_panel.move_requested.connect(self._on_session_move)
        self._session_panel.tags_edit_requested.connect(self._on_session_tags)
        self._session_panel.session_moved.connect(self._on_session_dropped)
        self._session_panel.group_rename_requested.connect(self._on_group_rename)
        self._session_panel.group_delete_requested.connect(self._on_group_delete)
```

- [ ] **Step 3: Add the handlers**

Add these methods (a `_current_backend()` helper returns the active session's backend or None):
```python
    def _current_backend(self):
        session = self._sessions.get(self._current)
        return session.backend if session else None

    def _on_session_filter(self, text: str) -> None:
        self._session_filter = text
        be = self._current_backend()
        if be is not None:
            self._populate_session_list(be)

    def _on_session_dropped(self, session_id: str, group: str) -> None:
        be = self._current_backend()
        if be is None:
            return
        AgentSessionMeta().set_group(be.display_name, session_id, group)
        self._populate_session_list(be)

    def _on_session_move(self, session_id: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        be = self._current_backend()
        if be is None:
            return
        meta = AgentSessionMeta()
        groups = all_groups(be.list_sessions(), meta, be.display_name)
        current = meta.get(be.display_name, session_id).group
        choices = groups + [""] if "" not in groups else groups
        idx = choices.index(current) if current in choices else 0
        name, ok = QInputDialog.getItem(
            self, "Move to group", "Group (blank = Ungrouped):", choices, idx, True)
        if ok:
            meta.set_group(be.display_name, session_id, name.strip())
            self._populate_session_list(be)

    def _on_session_tags(self, session_id: str) -> None:
        be = self._current_backend()
        if be is None:
            return
        meta = AgentSessionMeta()
        current = meta.get(be.display_name, session_id).tags
        known = all_tags(be.list_sessions(), meta, be.display_name)
        text = self._prompt_tags(", ".join(current), known)
        if text is None:
            return
        tags = []
        for raw in text.split(","):
            t = raw.strip()
            if t and t not in tags:
                tags.append(t)
        meta.set_tags(be.display_name, session_id, tags)
        self._populate_session_list(be)

    def _prompt_tags(self, current: str, known: list):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QLineEdit, QDialogButtonBox, QCompleter, QLabel)
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit tags")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Comma-separated tags:"))
        line = QLineEdit(current)
        completer = QCompleter(known, dlg)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        line.setCompleter(completer)

        def _token(text):
            completer.setCompletionPrefix(text.split(",")[-1].strip())

        def _accept(choice):
            parts = line.text().split(",")
            parts[-1] = " " + choice
            line.setText(", ".join(p.strip() for p in parts if p.strip()))
        line.textEdited.connect(_token)
        completer.activated.connect(_accept)
        v.addWidget(line)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        return line.text() if dlg.exec() else None

    def _on_group_rename(self, old: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        be = self._current_backend()
        if be is None:
            return
        new, ok = QInputDialog.getText(self, "Rename group", "New name:", text=old)
        if ok:
            AgentSessionMeta().rename_group(be.display_name, old, new.strip())
            self._populate_session_list(be)

    def _on_group_delete(self, group: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        be = self._current_backend()
        if be is None:
            return
        if QMessageBox.question(
                self, "Delete group",
                f"Ungroup all sessions in '{group}'? (sessions are kept)"
        ) == QMessageBox.StandardButton.Yes:
            AgentSessionMeta().delete_group(be.display_name, group)
            self._populate_session_list(be)
```

- [ ] **Step 4: Remove the dead `ordered_sessions`**

In `SciQLop/components/agents/chat/sessions_view.py`, delete the `ordered_sessions` function (now unused). In `tests/test_sessions_view.py`, delete the `test_pinned_first_then_mtime_desc_with_name_override` test (it targeted `ordered_sessions`). Confirm nothing else references it:
```
git grep -n "ordered_sessions" -- '*.py' ; echo "exit:$?"
```
Expected: nothing, `exit:1`.

- [ ] **Step 5: Verify — parse, no dangling refs, suites green**

```
uv run python -c "import ast; ast.parse(open('SciQLop/components/agents/chat_dock.py').read()); print('parse ok')"
git grep -n "set_sessions\|\.set_sessions(" SciQLop/components/agents/chat_dock.py ; echo "exit:$?"
uv run pytest --no-xvfb tests/test_session_meta_groups.py tests/test_sessions_view_groups.py tests/test_session_panel.py tests/test_session_meta.py tests/test_install_package_tool.py -q
```
Expected: `parse ok`; the `set_sessions` grep prints nothing (`exit:1`, the dock now calls `set_groups`); tests pass. Static self-check: every new handler uses attributes that exist (`self._sessions`, `self._current`, `self._session_panel`, `self._populate_session_list`, `AgentSessionMeta`) — confirm by grepping `chat_dock.py`.

- [ ] **Step 6: Manual smoke (record in report)**

Cannot launch the GUI headlessly. Note in the report that a human must confirm: groups render with the Pinned section on top; the filter box filters by name and tag; drag a session onto a group header moves it (and onto the empty area / Ungrouped ungroups it); right-click a session → Move to group… / Edit tags… (with autocomplete) work; right-click a group header → Rename group… / Delete group work; collapse state survives a re-render.

- [ ] **Step 7: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/chat_dock.py SciQLop/components/agents/chat/sessions_view.py tests/test_sessions_view.py
git commit -m "feat(agents): wire session groups/tags/filter into the chat dock

Grouped feed, filter box, move/tags dialogs (tag autocomplete), drag-drop moves,
group rename/delete. Removes the superseded ordered_sessions.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- group/tags fields + set_group/set_tags/rename_group/delete_group → Task 1.
- grouped_sessions ordering + filter + all_tags/all_groups → Task 2.
- Tree panel, filter box, drag-drop, session + group context menus, expand preservation, signals → Task 3.
- Filter re-render, move dialog, tag-edit dialog + QCompleter autocomplete, group rename/delete, drag-move, ordered_sessions removal → Task 4. ✓

**Placeholder scan:** none — full code and commands per step.

**Type consistency:** `DisplaySession(id,name,pinned,mtime,group,tags)`, `SessionGroup(name,sessions)`, `grouped_sessions(entries,meta,backend,filter_text)`, `all_tags`/`all_groups`, and the panel's nine signals + `set_groups` are used identically across Tasks 2-4; `AgentSessionMeta.set_group/set_tags/rename_group/delete_group(backend, …)` match Task 1 and Task 4; role constants `_ID_ROLE/_GROUP_ROLE/_KIND_ROLE` are internal to the panel and its tests.
