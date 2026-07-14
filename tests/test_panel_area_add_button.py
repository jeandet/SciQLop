from .fixtures import *
import PySide6QtAds as QtAds


def _area_for(main_window, panel):
    dw = main_window.dock_manager.findDockWidget(panel.name)
    return dw.dockAreaWidget()


def test_new_native_plot_panel_docks_into_explicit_area(main_window, qtbot):
    panel1 = main_window.new_plot_panel()
    try:
        area = _area_for(main_window, panel1)
        before = area.dockWidgetsCount()

        panel2 = main_window.new_native_plot_panel(area=area)
        try:
            qtbot.waitUntil(lambda: area.dockWidgetsCount() == before + 1, timeout=1000)
            assert _area_for(main_window, panel2) is area
        finally:
            main_window.remove_panel(panel2)
    finally:
        main_window.remove_panel(panel1)
