import shiboken6
from PySide6.QtCore import Qt, QRect, Signal, QEvent
from PySide6.QtGui import QPainter, QColor, QPainterPath, QRegion, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class CoachMark(QWidget):
    """Dims the main window except a spotlight cutout around a target
    widget, with an info bubble (title/body/dismiss/skip) beside it."""

    skip_requested = Signal()
    dismiss_clicked = Signal()
    target_destroyed = Signal()

    def __init__(self, main_window: QWidget):
        super().__init__(main_window)
        self._main_window = main_window
        self._target: QWidget | None = None
        self._target_local_rect: QRect | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._bubble = QWidget(self)
        layout = QVBoxLayout(self._bubble)
        self._title_label = QLabel(self._bubble)
        self._title_label.setStyleSheet("font-weight: bold;")
        self._body_label = QLabel(self._bubble)
        self._body_label.setWordWrap(True)
        buttons = QHBoxLayout()
        self._skip_link = QPushButton("Skip tour", self._bubble)
        self._skip_link.setFlat(True)
        self._skip_link.clicked.connect(self.skip_requested)
        self._dismiss_button = QPushButton("Got it", self._bubble)
        self._dismiss_button.clicked.connect(self.dismiss_clicked)
        buttons.addWidget(self._skip_link)
        buttons.addStretch(1)
        buttons.addWidget(self._dismiss_button)
        layout.addWidget(self._title_label)
        layout.addWidget(self._body_label)
        layout.addLayout(buttons)
        self._bubble.setStyleSheet(
            "background-color: palette(window); border-radius: 6px;")
        self._bubble.setFixedWidth(280)

        main_window.installEventFilter(self)
        self.hide()

    def show_for(self, target: QWidget, title: str, body: str, *,
                 rect: QRect | None = None, show_dismiss: bool = True) -> None:
        self._detach_target()
        self._target = target
        self._target_local_rect = rect
        target.installEventFilter(self)
        target.destroyed.connect(self._on_target_destroyed)
        self._title_label.setText(title)
        self._body_label.setText(body)
        self._dismiss_button.setVisible(show_dismiss)
        self.setGeometry(self._main_window.rect())
        self._reposition_bubble()
        self.show()
        self.raise_()
        self.setFocus()

    def dispose(self) -> None:
        """Detach from both the current target and `main_window` itself.

        Called exactly once, by TourController._finish(), when the owning
        tour is truly done. CoachMark has no notion of "the tour is over"
        on its own, so it must not remove its own main_window event filter
        anywhere else (e.g. its destructor) — only the controller knows
        when that's safe."""
        self._detach_target()
        if shiboken6.isValid(self._main_window):
            self._main_window.removeEventFilter(self)
        self.hide()

    def _detach_target(self) -> None:
        if self._target is None or not shiboken6.isValid(self._target):
            return
        self._target.removeEventFilter(self)
        try:
            self._target.destroyed.disconnect(self._on_target_destroyed)
        except RuntimeError:
            pass

    def _on_target_destroyed(self, *_):
        self._target = None
        self.hide()
        self.target_destroyed.emit()

    def eventFilter(self, obj, event):
        if obj is self._main_window and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move):
            self.setGeometry(self._main_window.rect())
            self._reposition_bubble()
        elif obj is self._target and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move):
            self._reposition_bubble()
        return False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.skip_requested.emit()
            return
        super().keyPressEvent(event)

    def _target_rect(self) -> QRect | None:
        if self._target is None:
            return None
        local_rect = self._target_local_rect or self._target.rect()
        top_left = self._target.mapTo(self._main_window, local_rect.topLeft())
        return QRect(top_left, local_rect.size())

    def _reposition_bubble(self) -> None:
        rect = self._target_rect()
        self._update_mask()
        if rect is None:
            return
        bubble_x = rect.right() + 12
        if bubble_x + self._bubble.sizeHint().width() > self.width():
            bubble_x = max(0, rect.left() - self._bubble.sizeHint().width() - 12)
        bubble_y = max(0, min(rect.top(), self.height() - self._bubble.sizeHint().height()))
        self._bubble.move(bubble_x, bubble_y)
        self._bubble.adjustSize()

    def _cutout_rect(self) -> QRect | None:
        rect = self._target_rect()
        if rect is None:
            return None
        return rect.adjusted(-4, -4, 4, 4)

    def _dimmed_path(self) -> QPainterPath:
        """The region that should actually block mouse input (and get
        painted dark): everything except the spotlight cutout around the
        target, so a click inside the cutout reaches the real widget behind
        it instead of this overlay."""
        path = QPainterPath()
        path.addRect(self.rect())
        cutout_rect = self._cutout_rect()
        if cutout_rect is not None:
            cutout = QPainterPath()
            cutout.addRoundedRect(cutout_rect, 6, 6)
            path = path.subtracted(cutout)
        return path

    def _update_mask(self) -> None:
        self.setMask(QRegion(self._dimmed_path().toFillPolygon().toPolygon()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillPath(self._dimmed_path(), QColor(0, 0, 0, 140))
        cutout_rect = self._cutout_rect()
        if cutout_rect is not None:
            # The mask (see _update_mask) excludes cutout_rect entirely so
            # clicks pass through it -- a stroke centered on cutout_rect's
            # own boundary would have its inner half clipped by that mask.
            # Draw it 1px further out so the full pen width stays on the
            # dimmed (visible) side.
            painter.setPen(QPen(self.palette().highlight().color(), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(cutout_rect.adjusted(-1, -1, 1, 1), 7, 7)
