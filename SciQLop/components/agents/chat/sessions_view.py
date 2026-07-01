"""Overlay backend sessions with custom name + pin metadata, ordered for display."""
from __future__ import annotations

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
