"""Task 9 — plot_product remote branch.

Verifies that when a product is registered as out_of_process, plot_product
builds a remote-backed graph (add_remote_color_map / add_remote_line_graph)
instead of the normal callback path.
"""
import numpy as np
import pytest
from tests.helpers import *  # noqa: F401,F403  — pulls in main_window, simple_vp_callback, etc.

# Module-level callbacks so cloudpickle can serialise them by reference.
def _spec_source(start: float, stop: float):
    t = np.linspace(start, stop, 8)
    f = np.linspace(10.0, 100.0, 5)
    z = np.random.rand(8, 5).astype(np.float32)
    return (t, f, z)


def _scalar_source(start: float, stop: float):
    t = np.linspace(start, stop, 16)
    return (t, np.sin(t))


# ---------------------------------------------------------------------------
# Registry isolation: reset the singleton so each test starts clean.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_registry():
    import SciQLop.components.plotting.backend.remote.registry as reg_mod
    old = reg_mod._REGISTRY
    reg_mod._REGISTRY = None
    yield
    # Shut down any workers spawned during the test before restoring the old registry.
    if reg_mod._REGISTRY is not None:
        try:
            reg_mod._REGISTRY.shutdown_all()
        except Exception:
            pass
    reg_mod._REGISTRY = old


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_plot_product_remote_spectrogram_builds_remote_graph(qtbot, main_window):
    """plot_product on an out_of_process spectrogram returns (plot, graph)
    where graph.remote_channel() is not None."""
    from SciQLop.components.plotting.backend.easy_provider import EasySpectrogram
    from SciQLop.components.plotting.ui.time_sync_panel import plot_product
    from SciQLop.user_api.plot import create_plot_panel

    EasySpectrogram(
        path="test_remote_plot/spec",
        get_data_callback=_spec_source,
        metadata={},
        out_of_process=True,
    )

    panel = create_plot_panel()
    result = plot_product(panel._impl, ["test_remote_plot", "spec"])

    assert result is not None, "plot_product must return a non-None result for a remote product"
    plot, graph = result
    assert plot is not None
    assert graph is not None
    assert graph.remote_channel() is not None, "remote graph must expose a RemoteDataPipeline"

    # Brief event pump: confirm no crash after setup.
    qtbot.wait(500)


def test_plot_product_remote_scalar_builds_remote_graph(qtbot, main_window):
    """plot_product on an out_of_process scalar returns (plot, graph) with a
    remote channel (line graph path, not colormap)."""
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import plot_product
    from SciQLop.user_api.plot import create_plot_panel

    EasyScalar(
        path="test_remote_plot/dens",
        get_data_callback=_scalar_source,
        component_name="dens",
        metadata={},
        out_of_process=True,
    )

    panel = create_plot_panel()
    result = plot_product(panel._impl, ["test_remote_plot", "dens"])

    assert result is not None
    plot, graph = result
    assert plot is not None
    assert graph is not None
    assert graph.remote_channel() is not None

    qtbot.wait(500)


def test_non_remote_product_unaffected(qtbot, main_window, simple_vp_callback):
    """plot_product on a normal (non-remote) product still follows the
    existing callback path and returns a valid (plot, graph) pair."""
    from SciQLop.user_api.virtual_products import create_virtual_product, VirtualProductType
    from SciQLop.components.plotting.ui.time_sync_panel import plot_product
    from SciQLop.user_api.plot import create_plot_panel, TimeRange

    vp = create_virtual_product(
        "test_remote_regression/normal_scalar",
        simple_vp_callback,
        VirtualProductType.Scalar,
        labels=["y"],
    )

    panel = create_plot_panel()
    panel.time_range = TimeRange(0.0, 10.0)
    result = plot_product(panel._impl, ["test_remote_regression", "normal_scalar"])

    assert result is not None, "non-remote plot_product must still work"
    plot, graph = result
    assert plot is not None
    assert graph is not None
    # Normal graphs do NOT have a remote_channel; the SciQLopPlots type is different.
    assert not hasattr(graph, "remote_channel") or graph.remote_channel() is None

    qtbot.wait(200)
