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
