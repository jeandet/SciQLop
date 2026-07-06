"""Task 8 — out_of_process opt-in: tagging and registry wiring.

Tests that an out_of_process=True virtual product:
  1. registers the product node in the products model,
  2. tags the node metadata with remote="True",
  3. records the path in the RemoteRegistry.
"""
import pytest
from tests.helpers import *  # noqa: F401,F403  — pulls in main_window, simple_vp_callback, etc.

from SciQLop.components.plotting.backend.remote.registry import remote_registry


# Reset the module-level singleton between tests so registry state doesn't bleed.
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


def test_out_of_process_scalar_tags_node_and_registers(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLopPlots import ProductsModel

    EasyScalar(
        path="test_remote/dens",
        get_data_callback=lambda start, stop: None,
        component_name="dens",
        metadata={},
        out_of_process=True,
    )

    node = ProductsModel.instance().node(["test_remote", "dens"])
    assert node is not None, "product node must exist in the products model"
    meta = node.metadata()
    assert meta.get("remote") in ("True", "true", True, "1"), (
        f"expected node.metadata()['remote'] to be truthy, got {meta.get('remote')!r}")
    assert remote_registry().is_remote(["test_remote", "dens"]), (
        "path must be recorded in the RemoteRegistry")


def test_out_of_process_false_does_not_register(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar

    EasyScalar(
        path="test_local/flux",
        get_data_callback=lambda start, stop: None,
        component_name="flux",
        metadata={},
        out_of_process=False,
    )

    assert not remote_registry().is_remote(["test_local", "flux"]), (
        "non-remote products must not appear in the RemoteRegistry")


def test_out_of_process_scalar_with_knobs_gets_knob_state(qtbot, main_window):
    from typing import Annotated
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.ui.time_sync_panel import plot_product
    from SciQLop.user_api.knobs import Knob
    from SciQLop.user_api.plot import create_plot_panel

    def f(start: float, stop: float,
          gain: Annotated[float, Knob(min=0.0, max=10.0)] = 2.0):
        import numpy as np
        return np.linspace(start, stop, 4), np.zeros(4)

    EasyScalar(
        path="test_remote_knobs/dens",
        get_data_callback=f,
        component_name="dens",
        metadata={},
        out_of_process=True,
    )

    panel = create_plot_panel()
    result = plot_product(panel._impl, ["test_remote_knobs", "dens"])

    assert result is not None
    plot, graph = result
    assert graph._remote_channel is not None
    assert graph._knob_state.values == {"gain": 2.0}

    qtbot.wait(500)
