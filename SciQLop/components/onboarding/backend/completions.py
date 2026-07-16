from PySide6.QtCore import QObject, QTimer, Signal


def panel_created(main_window, context):
    return main_window.panel_added


def dock_visible(dock_name):
    def _completion(main_window, context):
        dw = main_window.dock_manager.findDockWidget(dock_name)
        if dw is None:
            return None
        return dw.visibilityChanged, (lambda visible: visible)
    return _completion


class _PlotListSettled(QObject):
    """Bridges panel.plot_list_changed to a single `ready` signal that
    only fires once the panel's plot list has both (a) contained a real,
    non-placeholder plot, and (b) stopped changing for a short settle
    period. Reacting to the FIRST sighting of a real plot (what earlier
    onboarding fixes did, via panel.plot_added or the plot's own
    graph_list_changed) was not enough: SciQLopPlots/Wayland's
    drag-and-drop handling has been observed continuing to churn the
    panel's plot list (a second placeholder wave, the real plot itself
    getting destroyed) for a period after that first sighting. Waiting
    for the list to genuinely settle is robust to whatever that churn
    turns out to be, rather than needing to fully characterize it."""

    ready = Signal(object)

    _SETTLE_MS = 600

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_settled)
        panel.plot_list_changed.connect(self._on_plot_list_changed)

    def _has_real_plot(self, plots) -> bool:
        return any(p is not None and p.objectName() != "PlaceHolder" for p in plots)

    def _on_plot_list_changed(self, plots) -> None:
        if self._has_real_plot(plots):
            self._timer.start(self._SETTLE_MS)
        else:
            self._timer.stop()

    def _on_settled(self) -> None:
        real_plots = [p for p in self._panel.plots()
                     if p is not None and p.objectName() != "PlaceHolder"]
        if real_plots:
            self.ready.emit(real_plots[-1])


def plot_settled_in(context_key):
    def _completion(main_window, context):
        panel = context.get(context_key)
        if panel is None:
            return None
        waiter = _PlotListSettled(panel, parent=panel)
        return waiter.ready
    return _completion
