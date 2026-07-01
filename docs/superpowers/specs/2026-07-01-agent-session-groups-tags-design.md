# Agent session groups & tags

**Date:** 2026-07-01
**Status:** Approved (design)
**Repo:** SciQLop (in-tree only — extends the session panel; no backend/plugin change).

## Problem

The session panel (shipped) is a flat, pinned-first list. For real study work the
user wants to **group sessions into folders** (per study), **tag** them, and
**filter** by name/tag — plus manage groups (rename/delete), move sessions by
**drag & drop**, and get **tag autocomplete**.

## Decisions (from brainstorming)

- **Flat groups**, one group per session (no nesting). **Many tags** per session.
- **Filter box** matching name **or** any tag (case-insensitive substring).
- A synthetic **"📌 Pinned"** group on top (pinned sessions across all groups;
  they also still appear in their own group), then real groups **alphabetically**,
  then **"Ungrouped"** last.
- Group **rename/delete**, session **drag & drop** between groups, **tag
  autocomplete** — all included.
- Expand/collapse state preserved **in-session only** (not across restarts).

## Design

### 1. Metadata (`components/agents/settings.py`)

`SessionMetaEntry` gains:
```python
    group: str = ""
    tags: List[str] = Field(default_factory=list)
```
`AgentSessionMeta` gains (each mutates `entries` then `save()`):
- `set_group(backend, session_id, group)` / `set_tags(backend, session_id, tags)`
- `rename_group(backend, old, new)` — every entry under this backend with
  `group == old` gets `group = new`.
- `delete_group(backend, group)` — every such entry gets `group = ""`
  (sessions are never deleted, only ungrouped).

### 2. View model (`components/agents/chat/sessions_view.py`, pure)

- `DisplaySession` gains `group: str`, `tags: List[str]`.
- `@dataclass SessionGroup: name: str; sessions: List[DisplaySession]`.
- `grouped_sessions(entries, meta, backend, filter_text="") -> List[SessionGroup]`:
  1. Build `DisplaySession`s from entries+meta (name=`m.name or e.label`).
  2. **Filter:** drop those where `filter_text` (lowercased) is not a substring of
     the name or of any tag; empty `filter_text` keeps all.
  3. **Groups, in order:** a `"📌 Pinned"` group of all `pinned` sessions
     (mtime-desc) **iff any**; then real groups (`group != ""`) **sorted by group
     name**, each mtime-desc; then `"Ungrouped"` (`group == ""`) **iff any**.
     Empty groups omitted.
- `all_tags(entries, meta, backend) -> List[str]` — sorted unique tags in use
  (for autocomplete).
- `all_groups(entries, meta, backend) -> List[str]` — sorted unique non-empty
  group names (for the move dialog).
- The old flat `ordered_sessions` is superseded; remove it and its test if no
  longer referenced.

### 3. Panel (`components/agents/chat/session_panel.py`)

`QListWidget` → **`QTreeWidget`** (header hidden). New: a compact filter
`QLineEdit` above the tree.

- `set_groups(groups: List[SessionGroup], current_id=None)` — rebuild: one
  top-level item per `SessionGroup` (text `f"{name} ({len(sessions)})"`), child
  items per session (`("📌 " if pinned else "") + name`, with a right-aligned
  relative-age hint), session id in `UserRole`, group name on the header in
  `UserRole`. **Preserve expand state** by remembering the set of expanded group
  names across rebuilds (restore after repopulating; unknown groups default
  expanded).
- **Drag & drop:** `setDragDropMode(DragDrop)`, session items draggable, group
  headers (and the empty area) accept drops. Override the drop to compute the
  **target group** (the header dropped on, or `""`/Ungrouped for the empty area /
  Ungrouped header), emit `session_moved(id, group)`, and **ignore Qt's own move**
  (the tree is always rebuilt from data). Dropping onto a session resolves to that
  session's group. The `"📌 Pinned"` group is **not** a drop target (it's synthetic).
- **Context menus:**
  - session row → **Rename…** / **Pin·Unpin** / **Move to group…** / **Edit tags…**
  - group header (real groups only, not Pinned/Ungrouped) → **Rename group…** /
    **Delete group**
- **Signals:** existing `session_selected(str)`, `rename_requested(str)`,
  `pin_toggle_requested(str)` + new `filter_changed(str)`, `move_requested(str)`,
  `tags_edit_requested(str)`, `session_moved(str, str)`,
  `group_rename_requested(str)`, `group_delete_requested(str)`.

### 4. chat_dock integration

- Hold `self._session_filter = ""`. `_populate_session_list` →
  `grouped_sessions(backend.list_sessions(), AgentSessionMeta(),
  backend.display_name, self._session_filter)` → `panel.set_groups(...)`.
- `filter_changed` → store filter, re-populate.
- `move_requested(id)` → dialog offering `all_groups(...)` (editable combo /
  input); accept a new name; blank → Ungrouped → `set_group` → re-populate.
- `tags_edit_requested(id)` → dialog: comma-separated `QLineEdit` prefilled with
  the session's tags + a `QCompleter` over `all_tags(...)` completing the current
  token → parse (trim/dedupe/drop-empty) → `set_tags` → re-populate.
- `session_moved(id, group)` → `set_group` → re-populate.
- `group_rename_requested(old)` → input dialog (prefilled) → `rename_group` →
  re-populate. `group_delete_requested(old)` → confirm → `delete_group` →
  re-populate.
- Existing rename/pin handlers unchanged.

## Data flow

`list_sessions()` → `grouped_sessions(…, filter)` → `SessionGroup`s → tree.
Any edit (rename/pin/group/tags/move/group-rename/group-delete/filter) → mutate
`AgentSessionMeta` (or filter state) → `_populate_session_list` re-render.

## Error handling

- Missing metadata → default entry (empty group, no tags).
- Blank group name = Ungrouped. Renaming a group to blank = delete (ungroup).
- Duplicate/blank/whitespace tags collapsed on save.
- Dropping onto the synthetic Pinned group or an invalid target is a no-op.
- Deleting a group never deletes sessions.

## Testing (`uv run pytest --no-xvfb`)

- **settings:** `set_group`/`set_tags` round-trip; `rename_group` moves all
  members; `delete_group` ungroups all members (monkeypatched `save`).
- **sessions_view (pure):** `grouped_sessions` group order (Pinned-first, real
  groups alpha, Ungrouped last), within-group mtime-desc, empty-group omission,
  filter matches name and tags and excludes non-matches; `all_tags`/`all_groups`
  sorted-unique.
- **panel (`qtbot`):** `set_groups` builds headers+counts+children with 📌 and id
  roles; expand state preserved across rebuild; filter box emits `filter_changed`;
  session and group context menus emit the right signals; the drop handler
  (given a target item) emits `session_moved(id, target_group)` — tested via the
  internal drop-target resolver, not a simulated mouse drag.

## Out of scope

- Nested folders / sub-groups; session **delete**; cross-restart expand
  persistence; per-tag colored chips; bulk multi-select operations.
