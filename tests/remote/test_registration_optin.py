"""Task 8 — out_of_process opt-in: tagging and registry wiring.

Tests that an out_of_process=True virtual product:
  1. registers the product node in the products model,
  2. tags the node metadata with remote="True",
  3. records the path in the RemoteRegistry.
"""
import pytest

from SciQLop.components.plotting.backend.remote.registry import remote_registry


# Reset the module-level singleton between tests so registry state doesn't bleed.
@pytest.fixture(autouse=True)
def _isolate_registry():
    import SciQLop.components.plotting.backend.remote.registry as reg_mod
    old = reg_mod._REGISTRY
    reg_mod._REGISTRY = None
    yield
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
