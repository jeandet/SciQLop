"""Backward-compatible promotion of plot **kwargs to explicit keyword params."""
import numpy as np
import pytest
from .fixtures import *

from SciQLop.user_api.plot._graphs import _UNSET, _with_explicit


def test_with_explicit_forwards_set_values():
    kwargs = {"existing": 1}
    out = _with_explicit(kwargs, labels=["a", "b"], name="g")
    assert out is kwargs                      # mutates and returns the same dict
    assert out == {"existing": 1, "labels": ["a", "b"], "name": "g"}


def test_with_explicit_skips_unset_values():
    out = _with_explicit({}, labels=_UNSET, name="g", colors=_UNSET)
    assert out == {"name": "g"}               # _UNSET params are not forwarded


def test_with_explicit_unset_is_falsy_safe():
    # A real value that is falsy (False / [] / 0) must still be forwarded.
    out = _with_explicit({}, y_log_scale=False, labels=[], graph_type=0)
    assert out == {"y_log_scale": False, "labels": [], "graph_type": 0}


def _capture_panel_fn(monkeypatch, attr):
    """Spy that records the kwargs reaching a component-layer plot function
    and still delegates to the real one (so the graph is really created)."""
    import SciQLop.user_api.plot._panel as pm
    captured = {}
    original = getattr(pm, attr)

    def spy(impl, *args, **kwargs):
        captured.clear()
        captured.update(kwargs)
        return original(impl, *args, **kwargs)

    monkeypatch.setattr(pm, attr, spy)
    return captured


def test_plot_function_forwards_set_params_only(plot_panel, monkeypatch):
    captured = _capture_panel_fn(monkeypatch, "_plot_function")

    def f(start, stop):
        x = np.linspace(start, stop, 10)
        return x, np.sin(x)

    # Note: y_log_scale is only accepted by the SciQLopPlots colormap()
    # binding, not line() (the default graph_type here) — verified directly
    # against SciQLopPlots 0.29.2, and true of the *unmodified* plot_function
    # too, so this is a pre-existing library constraint, not something
    # introduced by this promotion. colors is used instead to exercise a
    # second "present" param; y_log_scale exercises the "absent" case.
    plot_panel.plot_function(f, labels=["s"], colors=["#ff0000"])
    assert captured["labels"] == ["s"]
    assert captured["colors"] == ["#ff0000"]
    assert "y_log_scale" not in captured       # omitted → not forwarded


def test_plot_function_name_hint_from_function_name(plot_panel):
    # `name` is applied via `set_name()` on the created graph rather than
    # forwarded through kwargs to `_plot_function` (SciQLopPlots' line()
    # binding rejects an upfront `name=` keyword — see the implementation
    # comment in _panel.py), so this is asserted on the real graph object
    # instead of via the `_capture_panel_fn` kwargs spy used above.
    def my_signal(start, stop):
        x = np.linspace(start, stop, 10)
        return x, np.sin(x)

    _, graph = plot_panel.plot_function(my_signal)
    assert graph._get_impl_or_raise().name == "my_signal"  # base name hint applied

    _, graph2 = plot_panel.plot_function(
        lambda s, e: (np.array([s, e]), np.array([0.0, 1.0])))
    assert graph2._get_impl_or_raise().name != "my_signal"  # <lambda> is skipped
