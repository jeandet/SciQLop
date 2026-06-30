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
