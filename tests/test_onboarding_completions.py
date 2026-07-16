from .fixtures import *


def test_panel_created_returns_panel_added_signal(main_window):
    from SciQLop.components.onboarding.backend.completions import panel_created
    assert panel_created(main_window, {}) is main_window.panel_added


def test_dock_visible_returns_none_when_dock_missing(main_window):
    from SciQLop.components.onboarding.backend.completions import dock_visible
    result = dock_visible("No Such Dock")(main_window, {})
    assert result is None


def test_dock_visible_predicate_filters_on_true(main_window):
    from SciQLop.components.onboarding.backend.completions import dock_visible
    signal, predicate = dock_visible("Products")(main_window, {})
    assert signal is main_window.dock_manager.findDockWidget("Products").visibilityChanged
    assert predicate(True) is True
    assert predicate(False) is False


def test_plot_populated_in_returns_none_when_context_key_missing():
    from SciQLop.components.onboarding.backend.completions import plot_populated_in
    assert plot_populated_in("create_panel")(None, {}) is None


def test_plot_populated_in_waits_for_data_not_just_plot_creation():
    """panel.plot_added fires the instant a plot WIDGET is inserted --
    including SciQLopPlots' PlaceHolderManager's temporary drag-preview
    PlaceHolder, before the user has even released the mouse, and
    including a real plot that's still empty (SciQLopMultiPlotPanel::
    dropEvent creates the plot shell via create_plot() before attaching
    any data to it). A live diagnostic run showed a freshly-created, real
    plot getting destroyed moments after an onboarding step targeted it
    off of plot_added alone -- something in SciQLopPlots/Wayland's
    drag-and-drop handling was still settling. plot_populated_in must
    reject the placeholder AND wait for the real plot's OWN
    graph_list_changed signal (fired once it actually has a graph/curve
    attached) before completing -- not just react to the plot widget's
    mere existence."""
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.backend.completions import plot_populated_in

    class _FakePlot(QObject):
        graph_list_changed = Signal()

    class _FakePanel(QObject):
        plot_added = Signal(object)

    panel = _FakePanel()
    context = {"create_panel": panel}
    signal = plot_populated_in("create_panel")(None, context)
    assert signal is not None

    received = []
    signal.connect(lambda plot: received.append(plot))

    placeholder = _FakePlot()
    placeholder.setObjectName("PlaceHolder")
    panel.plot_added.emit(placeholder)
    placeholder.graph_list_changed.emit()
    assert received == [], "a placeholder must never complete the step, even with data"

    real_plot = _FakePlot()
    real_plot.setObjectName("Plot")
    panel.plot_added.emit(real_plot)
    assert received == [], "the plot exists but has no data yet -- not complete"

    real_plot.graph_list_changed.emit()
    assert received == [real_plot], "now it actually has data -- complete"
