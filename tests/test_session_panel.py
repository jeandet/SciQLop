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
