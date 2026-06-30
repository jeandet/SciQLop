"""A session-list panel with rename/pin context actions for the agent chat dock."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel, QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QWidget,
)

_ID_ROLE = Qt.ItemDataRole.UserRole
_PIN_ROLE = Qt.ItemDataRole.UserRole + 1


class SessionListPanel(QWidget):
    session_selected = Signal(str)
    rename_requested = Signal(str)
    pin_toggle_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Sessions"))
        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.itemActivated.connect(self._on_activated)
        self._list.itemClicked.connect(self._on_activated)
        self._list.customContextMenuRequested.connect(self._on_menu)
        layout.addWidget(self._list, 1)

    def set_sessions(self, sessions, current_id=None) -> None:
        self._list.clear()
        for s in sessions:
            item = QListWidgetItem(("📌 " if s.pinned else "") + s.name)
            item.setData(_ID_ROLE, s.id)
            item.setData(_PIN_ROLE, bool(s.pinned))
            self._list.addItem(item)
            if current_id is not None and s.id == current_id:
                item.setSelected(True)

    def _on_activated(self, item) -> None:
        sid = item.data(_ID_ROLE) if item is not None else None
        if sid:
            self.session_selected.emit(sid)

    def _on_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        sid = item.data(_ID_ROLE)
        pinned = bool(item.data(_PIN_ROLE))
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.rename_requested.emit(sid))
        menu.addAction("Unpin" if pinned else "Pin",
                       lambda: self.pin_toggle_requested.emit(sid))
        menu.exec(self._list.mapToGlobal(pos))
