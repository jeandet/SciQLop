from .fixtures import *


def test_toolbar_hidden_by_default(main_window):
    assert main_window.toolBar.isVisible() is False


def test_view_menu_exposes_toolbar_toggle(main_window):
    assert main_window.toolBar.toggleViewAction() in main_window.viewMenu.actions()


def test_toolbar_toggle_action_shows_and_hides_toolbar(main_window, qtbot):
    toggle = main_window.toolBar.toggleViewAction()
    try:
        toggle.trigger()
        qtbot.waitUntil(lambda: main_window.toolBar.isVisible(), timeout=1000)
    finally:
        if main_window.toolBar.isVisible():
            toggle.trigger()
        qtbot.waitUntil(lambda: not main_window.toolBar.isVisible(), timeout=1000)
