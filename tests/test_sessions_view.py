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
