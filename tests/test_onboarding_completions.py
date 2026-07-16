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
