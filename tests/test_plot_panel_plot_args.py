"""Reproducers for PlotPanel.plot argument-forwarding bugs (2026-06-09 review):
- static-data branch dropped plot_index (always created a new subplot)
- product=/callback= keyword forms collided with the forwarded **kwargs
"""
from .fixtures import *
import pytest
import numpy as np


def _xy(n=50):
    x = np.linspace(0.0, 100.0, n)
    return x, np.sin(x)


def test_plot_static_data_respects_plot_index(plot_panel):
    x, y = _xy()
    plot_panel.plot(x, y)
    assert len(plot_panel.plots) == 1

    result = plot_panel.plot(x, y * 2.0, plot_index=0)
    assert result is not None
    assert len(plot_panel.plots) == 1, \
        "plot(x, y, plot_index=0) must add a graph to subplot 0, not append a new subplot"


def test_plot_static_data_default_appends(plot_panel):
    x, y = _xy()
    plot_panel.plot(x, y)
    plot_panel.plot(x, y * 2.0)
    assert len(plot_panel.plots) == 2


def test_fluent_plot_overlays_on_current_subplot(main_window):
    from SciQLop.user_api.plot import fluent
    x, y = _xy()
    builder = fluent.new_panel().plot(x, y).plot(x, y * 2.0)
    assert len(builder.panel.plots) == 1, \
        "two .plot() calls without .subplot() must share one subplot"
    builder.subplot().plot(x, y * 3.0)
    assert len(builder.panel.plots) == 2


def test_plot_callback_keyword(plot_panel):
    def cb(start: float, stop: float):
        x = np.linspace(start, stop, 10)
        return x, np.cos(x)

    result = plot_panel.plot(callback=cb)
    assert result is not None
    plot, graph = result
    assert plot is not None
    assert graph is not None


def test_plot_unrecognized_args_raise(plot_panel):
    with pytest.raises(ValueError, match="plot\\(\\) could not interpret"):
        plot_panel.plot()
    with pytest.raises(ValueError, match="plot\\(\\) could not interpret"):
        plot_panel.plot(42)


def test_plot_product_keyword(plot_panel, simple_vp_callback):
    from SciQLop.user_api.virtual_products import (
        create_virtual_product, VirtualProductType,
    )
    vp = create_virtual_product("test_plot_product_kw/vp1", simple_vp_callback,
                                VirtualProductType.Scalar, labels=["y"])
    result = plot_panel.plot(product=vp)
    assert result is not None
    plot, graph = result
    assert plot is not None
    assert graph is not None
