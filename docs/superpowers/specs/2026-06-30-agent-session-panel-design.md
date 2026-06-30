# Agent session panel — rename, pin, resizeable/hideable list

**Date:** 2026-06-30
**Status:** Approved (design)
**Repo:** SciQLop (in-tree only — no backend protocol or plugin changes).

## Problem

Agent sessions are presented as a single per-backend dropdown (`_session_combo`
in `chat_dock.py`, "Resume a previous session"), populated from
`backend.list_sessions() -> List[SessionEntry(id, label, mtime)]`. Labels are
derived by the backend; there is no way to rename a session, pin important ones,
or browse them comfortably.

## Design

Sessions stay owned by their SDK/CLI. SciQLop adds a **metadata overlay** (custom
name + pinned flag) and replaces the dropdown with a **resizeable, hideable
session-list panel**. Three small in-tree units; no `AgentBackend` protocol or
plugin change.

### 1. Metadata store — `AgentSessionMeta` (ConfigEntry)

In `SciQLop/components/agents/settings.py`:

```python
class SessionMetaEntry(BaseModel):
    name: str = ""
    pinned: bool = False

class AgentSessionMeta(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Agent chat"
    entries: Dict[str, SessionMetaEntry] = Field(
        default_factory=dict, json_schema_extra={"widget": "hidden"})
```

- Key format: `f"{backend}/{session_id}"` (global; pins/names follow the session).
- Helpers (mutate + `save()`): `get(backend, id) -> SessionMetaEntry` (returns a
  default empty entry if absent), `set_name(backend, id, name)`,
  `set_pinned(backend, id, pinned)`. `widget: "hidden"` keeps it out of the
  settings UI (it is internal state).

### 2. Pure ordering overlay

```python
@dataclass
class DisplaySession:
    id: str
    name: str       # custom name, else the backend's derived label
    pinned: bool
    mtime: float

def ordered_sessions(entries: list[SessionEntry], meta: AgentSessionMeta,
                     backend: str) -> list[DisplaySession]:
```

For each `SessionEntry`, apply `meta.get(backend, e.id)`: `name = m.name or
e.label`, `pinned = m.pinned`. Sort **pinned first, then `mtime` descending**
(`key=lambda d: (not d.pinned, -d.mtime)`). Pure → unit-testable, no Qt. Lives in
a small module (e.g. `components/agents/chat/sessions_view.py`).

### 3. UI

**`SessionListPanel(QWidget)`** (new, focused, testable) — a `QListWidget` plus a
small header (title + refresh). API:
- `set_sessions(list[DisplaySession], current_id)` — repopulate; pinned rows show
  a 📌 prefix and group at the top; each row stores its id; mtime shown right-aligned.
- Signals: `session_selected(str id)`, `rename_requested(str id)`,
  `pin_toggle_requested(str id)`.
- Right-click a row → `QMenu`: **Rename…**, **Pin**/**Unpin** (label by current
  state) → emits the corresponding signal. Left-click/activate → `session_selected`.

**`chat_dock` integration:**
- Wrap the transcript area in a `QSplitter(Qt.Horizontal)` with the
  `SessionListPanel` on the left and the transcript on the right;
  `setCollapsible(0, True)`, a sensible min-width and initial size.
- Remove `_session_combo`; populate the panel via `ordered_sessions(...)` wherever
  the combo was populated (`_populate_session_list`). Selecting a row runs the
  existing resume/load path (`load_session`/resume) the combo used.
- `rename_requested` → `QInputDialog.getText` (prefilled with current name) →
  `AgentSessionMeta.set_name` → re-render. `pin_toggle_requested` →
  `set_pinned(not current)` → re-render.
- **Hideable:** a checkable header toggle button (a sidebar/"Sessions" button)
  shows/hides the panel. **Resizeable:** the splitter handle.
- **Persisted UI state** (two fields on the existing `AgentChatSettings`):
  `sessions_pane_visible: bool = True`, `sessions_pane_width: int = 280`. Restore
  on dock creation; write on toggle and on `splitterMoved` (debounced/last-value).
- If the active backend has `supports_sessions == False`, hide/disable the panel
  (as the combo was effectively unused there).

## Data flow

`backend.list_sessions()` → `ordered_sessions(entries, meta, backend)` → rows in
`SessionListPanel`. Row click → resume/load (unchanged). Rename/pin → mutate
`AgentSessionMeta` → re-render. Toggle/drag → update `AgentChatSettings`.

## Error handling

- Missing metadata → default `SessionMetaEntry()` (empty name, not pinned).
- A renamed-to-empty string → falls back to the derived label (treat blank as
  "clear the custom name").
- Backend without sessions → panel hidden/empty; no crash.
- The overlay never mutates the backend's `SessionEntry`s.

## Testing (SciQLop test env, `uv run pytest --no-xvfb`)

- `AgentSessionMeta`: `set_name`/`set_pinned` then reload a fresh instance →
  values persist (YAML round-trip); `get` returns a default for unknown keys.
- `ordered_sessions` (pure): pinned entries first; custom name overrides label,
  blank name falls back to label; `mtime`-descending within each group.
- `SessionListPanel` (`pytest-qt`/`qtbot`): `set_sessions` builds the expected
  rows in order with the 📌 marker on pinned; activating a row emits
  `session_selected` with the right id; the context menu emits
  `rename_requested`/`pin_toggle_requested`.

## Out of scope

- **Delete** sessions (would need a new `AgentBackend.delete_session` per plugin).
- Protecting pinned sessions from SDK-side pruning (SciQLop doesn't control it).
- Per-workspace metadata, cross-backend session dedup, drag-reorder.
