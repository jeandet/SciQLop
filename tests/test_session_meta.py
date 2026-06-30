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
    saved.clear()  # ignore the construction-time save; count only mutations
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
