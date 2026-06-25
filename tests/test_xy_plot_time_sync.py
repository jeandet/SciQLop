"""Auto time-sync of callback graphs in plain XY plots.

SciQLop.user_api.plot / time_sync_panel are imported INSIDE tests on purpose:
a top-level import touches the ProductsModel Qt global static before a
QApplication exists and aborts during collection.
"""
from .fixtures import *
import numpy as np
import pytest


def test_xy_function_plot_is_time_synced_to_panel(plot_panel, qtbot):
    from SciQLop.core import TimeRange
    from SciQLop.user_api.plot import PlotType

    seen = []

    def spectrum(start, stop):
        seen.append((float(start), float(stop)))
        return np.linspace(0.01, 1.0, 16), np.ones(16)

    t0 = 1.7e9
    # a time-series anchor on plot 0
    plot_panel.plot_data(np.array([t0, t0 + 1, t0 + 2]),
                         np.array([1.0, 2.0, 3.0]))
    # XY function on a new plot — NO manual time_range_changed.connect
    plot_panel.plot_function(spectrum, plot_index=1, plot_type=PlotType.XY,
                             labels=["spec"])

    seen.clear()
    plot_panel.time_range = TimeRange(t0 + 200, t0 + 300)
    qtbot.wait(80)

    assert seen, "XY function callback was not invoked on a panel time-range change"
    assert seen[-1] == pytest.approx((t0 + 200, t0 + 300))


def test_timeseries_function_plot_still_time_synced(plot_panel, qtbot):
    """The no-op path: time-series function plots already observe the time
    axis (their X axis), and must keep refreshing on time changes."""
    from SciQLop.core import TimeRange

    seen = []

    def line(start, stop):
        seen.append((float(start), float(stop)))
        t = np.linspace(start, stop, 10)
        return t, np.sin(t)

    plot_panel.plot_function(line)  # default plot_type=TimeSeries

    seen.clear()
    t0 = 1.7e9
    plot_panel.time_range = TimeRange(t0, t0 + 50)
    qtbot.wait(80)

    assert seen, "time-series function callback not invoked on time change"
    assert seen[-1] == pytest.approx((t0, t0 + 50))


def test_gate_excludes_timeseries_and_projection(qapp):
    """`_is_plain_xy_plot` keys off the C++ class name so it works on both
    concrete plots and SciQLopPlotInterfacePtr handles."""
    from SciQLop.components.plotting.ui.time_sync_panel import _is_plain_xy_plot

    class _FakeMeta:
        def __init__(self, name):
            self._name = name

        def className(self):
            return self._name

    class _FakePlot:
        def __init__(self, name):
            self._meta = _FakeMeta(name)

        def metaObject(self):
            return self._meta

    assert _is_plain_xy_plot(_FakePlot("SciQLopPlot")) is True
    assert _is_plain_xy_plot(_FakePlot("SciQLopTimeSeriesPlot")) is False
    assert _is_plain_xy_plot(_FakePlot("SciQLopNDProjectionPlot")) is False
