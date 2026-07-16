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


def test_plot_settled_in_returns_none_when_context_key_missing():
    from SciQLop.components.onboarding.backend.completions import plot_settled_in
    assert plot_settled_in("create_panel")(None, {}) is None


def test_plot_settled_in_waits_for_the_list_to_stop_churning(qtbot):
    """Reacting to the FIRST sighting of a real (non-placeholder) plot in
    the panel's plot list isn't enough -- SciQLopPlots/Wayland's
    drag-and-drop handling has been observed continuing to churn the
    panel's plot list (a second placeholder wave, the real plot itself
    getting destroyed) for a period after that first sighting; earlier
    onboarding fixes that acted on the first sighting (panel.plot_added,
    the plot's own graph_list_changed) were not enough. plot_settled_in
    must wait for panel.plot_list_changed to stop firing for a short
    settle period before completing, so it's robust to whatever the
    churn turns out to be, using the last real plot once things settle."""
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.backend import completions
    from SciQLop.components.onboarding.backend.completions import plot_settled_in, _PlotListSettled

    monkeypatch_settle_ms = 50
    original_settle_ms = _PlotListSettled._SETTLE_MS
    _PlotListSettled._SETTLE_MS = monkeypatch_settle_ms
    try:
        class _FakePlot(QObject):
            def __init__(self, name):
                super().__init__()
                self.setObjectName(name)

        class _FakePanel(QObject):
            plot_list_changed = Signal(list)

            def __init__(self):
                super().__init__()
                self._current_plots = []

            def plots(self):
                return self._current_plots

        panel = _FakePanel()
        context = {"create_panel": panel}
        signal = plot_settled_in("create_panel")(None, context)
        assert signal is not None

        received = []
        signal.connect(lambda plot: received.append(plot))

        placeholder = _FakePlot("PlaceHolder")
        panel._current_plots = [placeholder]
        panel.plot_list_changed.emit(panel._current_plots)
        qtbot.wait(monkeypatch_settle_ms // 2)
        assert received == [], "placeholder alone must never complete the step"

        real_plot = _FakePlot("Plot")
        panel._current_plots = [real_plot]
        panel.plot_list_changed.emit(panel._current_plots)
        qtbot.wait(monkeypatch_settle_ms // 2)
        assert received == [], "must not complete on the first sighting -- give it time to settle"

        # More churn arrives before the settle period elapses -- must reset the wait.
        placeholder2 = _FakePlot("PlaceHolder")
        panel._current_plots = [real_plot, placeholder2]
        panel.plot_list_changed.emit(panel._current_plots)

        qtbot.wait(monkeypatch_settle_ms * 3)
        assert received == [real_plot], (
            "settled after the churn stopped -- now complete, with the last real plot")
    finally:
        _PlotListSettled._SETTLE_MS = original_settle_ms
