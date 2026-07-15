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


def test_plot_added_to_reads_panel_from_context(main_window):
    from SciQLop.components.onboarding.backend.completions import plot_added_to
    fake_panel = type("FakePanel", (), {"plot_added": "sentinel"})()
    context = {"create_panel": fake_panel}
    signal, predicate = plot_added_to("create_panel")(main_window, context)
    assert signal == "sentinel"


def test_plot_added_to_returns_none_when_context_key_missing():
    from SciQLop.components.onboarding.backend.completions import plot_added_to
    assert plot_added_to("create_panel")(None, {}) is None


def test_plot_added_to_predicate_rejects_the_drag_preview_placeholder():
    """PlaceHolderManager (SciQLopPlots) inserts a temporary PlaceHolder
    plot into the panel on dragEnterEvent/dragMoveEvent -- before the user
    has even released the mouse -- and that insertion fires plot_added
    the same as a real plot. If the onboarding step's completion accepted
    that emission, it would advance mid-drag, target the placeholder in
    the next step, and then abort the whole tour the moment the
    placeholder gets torn down on drop. The predicate must reject any
    plot whose objectName is "PlaceHolder" (how SciQLopPlotInterface's
    constructor names it) and accept anything else."""
    from SciQLop.components.onboarding.backend.completions import plot_added_to
    fake_panel = type("FakePanel", (), {"plot_added": "sentinel"})()
    context = {"create_panel": fake_panel}
    _signal, predicate = plot_added_to("create_panel")(None, context)

    placeholder = type("FakePlot", (), {"objectName": lambda self: "PlaceHolder"})()
    real_plot = type("FakePlot", (), {"objectName": lambda self: "Plot_1"})()

    assert predicate(placeholder) is False
    assert predicate(real_plot) is True
