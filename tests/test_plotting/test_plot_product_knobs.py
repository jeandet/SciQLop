from typing import Annotated

import numpy as np
import pytest

from SciQLop.user_api.knobs import Knob, IntKnob


def test_attach_knob_state_populates_graph_and_callback(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.backend.graph_knobs import GraphKnobState
    from SciQLop.components.plotting.ui.time_sync_panel import (
        _attach_knob_state,
        _plot_product_callback,
    )
    from PySide6.QtCore import QObject

    def f(start: float, stop: float,
          fft: Annotated[int, Knob(min=64, max=4096)] = 256):
        n = 4
        return np.linspace(start, stop, n), np.zeros(n)

    provider = EasyScalar(path="vp/knobtest", get_data_callback=f, component_name="x", metadata={})
    graph = QObject()
    callback = _plot_product_callback(provider=provider, node=None)

    _attach_knob_state(provider, "vp/knobtest", callback, graph)

    state = getattr(graph, "_knob_state", None)
    assert state is not None
    assert state.values == {"fft": 256}
    assert callback.knob_state is state


def test_attach_knob_state_no_op_for_no_knobs(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import (
        _attach_knob_state,
        _plot_product_callback,
    )
    from PySide6.QtCore import QObject

    def f(start: float, stop: float):
        n = 4
        return np.linspace(start, stop, n), np.zeros(n)

    provider = EasyScalar(path="vp/noknobs", get_data_callback=f, component_name="x", metadata={})
    graph = QObject()
    callback = _plot_product_callback(provider=provider, node=None)

    _attach_knob_state(provider, "vp/noknobs", callback, graph)

    assert not hasattr(graph, "_knob_state")
    assert callback.knob_state is None


def test_attach_knob_state_knobs_changed_signal_fires(qapp, qtbot):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import (
        _attach_knob_state,
        _plot_product_callback,
    )
    from PySide6.QtCore import QObject

    def f(start: float, stop: float,
          fft: Annotated[int, Knob(min=64, max=4096)] = 256):
        n = 4
        return np.linspace(start, stop, n), np.zeros(n)

    provider = EasyScalar(path="vp/signaltest", get_data_callback=f, component_name="x", metadata={})
    graph = QObject()
    callback = _plot_product_callback(provider=provider, node=None)

    _attach_knob_state(provider, "vp/signaltest", callback, graph)

    state = graph._knob_state
    fired = []
    state.knobs_changed.connect(lambda d: fired.append(d))
    state.set_value("fft", 512)
    assert fired == [{"fft": 512}]


class _FakeRemoteChannel:
    def __init__(self):
        self.knobs_calls = []

    def set_knobs(self, knobs):
        self.knobs_calls.append(dict(knobs))

    def on_data_requested_values(self, start, stop):
        pass


def test_attach_remote_knob_state_binds_channel(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import _attach_remote_knob_state
    from PySide6.QtCore import QObject

    def f(start: float, stop: float,
          gain: Annotated[float, Knob(min=0.0, max=10.0)] = 1.0):
        return np.linspace(start, stop, 4), np.zeros(4)

    provider = EasyScalar(path="vp/remoteknobtest", get_data_callback=f, component_name="x", metadata={})
    graph = QObject()
    channel = _FakeRemoteChannel()

    _attach_remote_knob_state(provider, "vp/remoteknobtest", channel, graph)

    state = graph._knob_state
    assert state.values == {"gain": 1.0}
    assert channel.knobs_calls == [{"gain": 1.0}]   # initial bind

    state.set_value("gain", 5.0)
    assert channel.knobs_calls[-1] == {"gain": 5.0}


def test_attach_remote_knob_state_no_op_for_no_knobs(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import _attach_remote_knob_state
    from PySide6.QtCore import QObject

    def f(start: float, stop: float):
        return np.linspace(start, stop, 4), np.zeros(4)

    provider = EasyScalar(path="vp/remotenoknobs", get_data_callback=f, component_name="x", metadata={})
    graph = QObject()
    channel = _FakeRemoteChannel()

    _attach_remote_knob_state(provider, "vp/remotenoknobs", channel, graph)

    assert not hasattr(graph, "_knob_state")
    assert channel.knobs_calls == []

