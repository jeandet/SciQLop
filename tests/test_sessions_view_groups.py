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
