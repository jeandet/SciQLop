import pytest

from SciQLop.components.plotting.backend.dependencies import (
    DependsSpec, describe_target, resolve_dependency,
)


def test_resolve_callable_applies_pad():
    seen = {}
    def upstream(start, stop):
        seen["range"] = (start, stop)
        return ("UPSTREAM",)
    spec = DependsSpec(name="b", target=upstream, pad=5.0)
    result = resolve_dependency(spec, 100.0, 200.0)
    assert result == ("UPSTREAM",)
    assert seen["range"] == (95.0, 205.0)


def test_cycle_depth_guard_raises():
    holder = {}
    def recursive(start, stop):
        return resolve_dependency(holder["spec"], start, stop)
    spec = DependsSpec(name="x", target=recursive, pad=0.0)
    holder["spec"] = spec
    with pytest.raises(RecursionError) as ei:
        resolve_dependency(spec, 0.0, 1.0)
    assert "cycle" in str(ei.value).lower()


def test_describe_target_for_path_and_list():
    assert describe_target("a//b") == "a//b"
    assert describe_target(["a", "b"]) == "a//b"


def test_describe_target_for_callable():
    def myfunc(start, stop):
        return None
    assert "myfunc" in describe_target(myfunc)


def test_depth_restored_after_non_cycle_exception():
    def boom(start, stop):
        raise RuntimeError("nope")
    spec = DependsSpec(name="b", target=boom, pad=0.0)
    with pytest.raises(RuntimeError):
        resolve_dependency(spec, 0.0, 1.0)

    # depth must be back to 0 so a fresh successful call works
    def ok(start, stop):
        return ("OK",)
    assert resolve_dependency(DependsSpec(name="c", target=ok, pad=0.0), 0.0, 1.0) == ("OK",)
