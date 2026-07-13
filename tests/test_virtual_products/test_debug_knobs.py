from tests.fixtures import *



def _find_knob_state(panel):
    for plot in panel.plots():
        for graph in plot.plottables():
            state = getattr(graph, "_knob_state", None)
            if state is not None:
                return state
        for child in plot.children():
            state = getattr(child, "_knob_state", None)
            if state is not None:
                return state
    return None


def test_debug_replot_preserves_knob_values(qtbot, qapp, main_window):
    from SciQLop.user_api.virtual_products.magic import vp_magic, _registry

    cell = (
        "from typing import Annotated\n"
        "from SciQLop.user_api.knobs import Knob\n"
        "def my_vp(start: float, stop: float,\n"
        "          fft: Annotated[int, Knob(min=64, max=4096)] = 256) -> Scalar:\n"
        "    import numpy as np\n"
        "    n = 8\n"
        "    return np.linspace(start, stop, n), np.zeros(n) + fft\n"
    )
    vp_magic("--debug --start 0 --stop 10", cell)

    def _has_knob_state():
        panel = getattr(_registry.get("my_vp"), "panel", None)
        return panel is not None and _find_knob_state(panel) is not None

    qtbot.waitUntil(_has_knob_state, timeout=1000)
    entry = _registry.get("my_vp")
    assert entry is not None
    assert entry.panel is not None
    assert entry.panel.plots(), "debug panel should have a plot"
    state = _find_knob_state(entry.panel)
    assert state.values["fft"] == 256

    state.set_value("fft", 1024)
    qtbot.wait(50)

    vp_magic("--debug --start 0 --stop 10", cell)
    qtbot.waitUntil(lambda: _find_knob_state(entry.panel) is not None, timeout=1000)
    new_state = _find_knob_state(entry.panel)
    assert new_state.values["fft"] == 1024


def test_restore_drops_unknown_and_fills_defaults_missing():
    from SciQLop.user_api.knobs import IntKnob
    from SciQLop.components.plotting.backend.graph_knobs import GraphKnobState

    state = GraphKnobState([
        IntKnob(name="fft", default=256, min=64, max=4096),
    ])
    state.set_all({"fft": 1024, "old_knob": 5})
    assert state.values == {"fft": 1024}


def test_restore_applies_snapshot_values_to_current_specs():
    from SciQLop.user_api.knobs import IntKnob, ChoiceKnob
    from SciQLop.components.plotting.backend.graph_knobs import GraphKnobState

    state = GraphKnobState([
        IntKnob(name="fft", default=256, min=64, max=4096),
        ChoiceKnob(name="win", default="hann",
                   choices=(("Hann", "hann"), ("Hamming", "hamming"))),
    ])
    state.set_all({"fft": 1024, "win": "hamming", "stray": 99})
    assert state.values == {"fft": 1024, "win": "hamming"}
