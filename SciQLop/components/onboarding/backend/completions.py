from PySide6.QtCore import QObject, Signal


def panel_created(main_window, context):
    return main_window.panel_added


def dock_visible(dock_name):
    def _completion(main_window, context):
        dw = main_window.dock_manager.findDockWidget(dock_name)
        if dw is None:
            return None
        return dw.visibilityChanged, (lambda visible: visible)
    return _completion


class _PlotDataReady(QObject):
    """Bridges panel.plot_added (fires the instant a plot WIDGET is
    inserted -- real or SciQLopPlots' drag-preview PlaceHolder, and even
    a real plot that's still empty) to a single `ready` signal that only
    fires once a REAL plot has actually received data
    (graph_list_changed). A plot widget existing is not the same as the
    drop being finished -- a live diagnostic run showed a freshly-created,
    still-empty real plot getting destroyed moments after an onboarding
    step targeted it, from SciQLopPlots/Wayland drag-and-drop handling
    still settling. Waiting for the plot's first graph is a direct
    "the drop actually landed" signal, not just "a widget exists"."""

    ready = Signal(object)

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self._real_plot = None
        panel.plot_added.connect(self._on_plot_added)

    def _on_plot_added(self, plot):
        if self._real_plot is not None or plot.objectName() == "PlaceHolder":
            return
        self._real_plot = plot
        plot.graph_list_changed.connect(self._on_graph_list_changed)

    def _on_graph_list_changed(self):
        self.ready.emit(self._real_plot)


def plot_populated_in(context_key):
    def _completion(main_window, context):
        panel = context.get(context_key)
        if panel is None:
            return None
        waiter = _PlotDataReady(panel, parent=panel)
        return waiter.ready
    return _completion
