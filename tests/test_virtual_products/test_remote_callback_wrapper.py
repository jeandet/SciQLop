from datetime import datetime, timezone

from pydantic import BaseModel

from SciQLop.components.plotting.backend.easy_provider import (
    _build_remote_callback, _to_datetime,
)


def test_remote_callback_passes_through_plain_kwargs():
    calls = []

    def cb(start, stop, gain=1.0):
        calls.append((start, stop, gain))
        return None

    remote_cb = _build_remote_callback(cb, range_stack=[], knobs_model=None, knobs_kwarg_name="knobs")
    remote_cb(0.0, 10.0, gain=3.0)
    assert calls == [(0.0, 10.0, 3.0)]


def test_remote_callback_defaults_to_empty_knobs():
    calls = []

    def cb(start, stop):
        calls.append((start, stop))
        return None

    remote_cb = _build_remote_callback(cb, range_stack=[], knobs_model=None, knobs_kwarg_name="knobs")
    remote_cb(0.0, 10.0)
    assert calls == [(0.0, 10.0)]


def test_remote_callback_applies_range_stack():
    calls = []

    def cb(start, stop):
        calls.append((start, stop))
        return None

    remote_cb = _build_remote_callback(
        cb, range_stack=[lambda rng: _to_datetime(*rng)],
        knobs_model=None, knobs_kwarg_name="knobs")
    remote_cb(0.0, 10.0)
    assert calls == [(datetime.fromtimestamp(0.0, tz=timezone.utc),
                       datetime.fromtimestamp(10.0, tz=timezone.utc))]


def test_remote_callback_constructs_knobs_model():
    calls = []

    class Knobs(BaseModel):
        gain: float = 1.0

    def cb(start, stop, knobs):
        calls.append((start, stop, knobs))
        return None

    remote_cb = _build_remote_callback(cb, range_stack=[], knobs_model=Knobs, knobs_kwarg_name="knobs")
    remote_cb(0.0, 10.0, gain=5.0)
    assert calls == [(0.0, 10.0, Knobs(gain=5.0))]


def test_remote_callback_preserves_module_and_qualname_for_plugin_key():
    """RemoteRegistry.plugin_key_for() groups workers by callback.__module__ —
    the wrapper must look like the original callback, not like easy_provider,
    or every plugin's out_of_process VPs would collapse onto one worker."""
    def cb(start, stop):
        return None

    remote_cb = _build_remote_callback(cb, range_stack=[], knobs_model=None, knobs_kwarg_name="knobs")
    assert remote_cb.__module__ == cb.__module__
    assert remote_cb.__qualname__ == cb.__qualname__


import pytest
from typing import Annotated

from speasy.products import SpeasyVariable

from SciQLop.components.plotting.backend.dependencies import Depends


def test_out_of_process_with_debug_raises(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar

    with pytest.raises(ValueError, match="debug"):
        EasyScalar(path="test_remote_guard/debug", get_data_callback=lambda s, e: None,
                   component_name="x", metadata={}, out_of_process=True, debug=True)


def test_out_of_process_with_dependency_raises(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar

    def cb(start: float, stop: float,
           dep: Annotated[SpeasyVariable, Depends("speasy//amda//imf")] = None):
        return None

    with pytest.raises(ValueError, match="Depends"):
        EasyScalar(path="test_remote_guard/dep", get_data_callback=cb,
                   component_name="x", metadata={}, out_of_process=True)


def test_out_of_process_without_debug_or_deps_still_registers(qapp):
    from SciQLop.components.plotting.backend.easy_provider import EasyScalar
    from SciQLop.components.plotting.backend.remote.registry import remote_registry
    import SciQLop.components.plotting.backend.remote.registry as reg_mod

    old = reg_mod._REGISTRY
    reg_mod._REGISTRY = None
    try:
        EasyScalar(path="test_remote_guard/ok", get_data_callback=lambda s, e: None,
                   component_name="x", metadata={}, out_of_process=True)
        assert remote_registry().is_remote(["test_remote_guard", "ok"])
    finally:
        if reg_mod._REGISTRY is not None:
            reg_mod._REGISTRY.shutdown_all()
        reg_mod._REGISTRY = old
