"""sciqlop_ephemeris / sciqlop_transform / sciqlop_orbit_bodies_and_frames
registration + handler wiring (needs QApplication -> qtbot)."""
import asyncio
from unittest.mock import MagicMock


def _tool(qtbot, name):
    import SciQLop.components.agents.tools._builder as builder
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_bodies_and_frames_tool_registered_read_only(qtbot):
    t = _tool(qtbot, "sciqlop_orbit_bodies_and_frames")
    assert t.get("gated", False) is False
    assert t["input_schema"]["required"] == []


def test_ephemeris_tool_registered_gated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_ephemeris")
    assert t.get("gated", False) is True
    props = t["input_schema"]["properties"]
    assert set(t["input_schema"]["required"]) == {"body", "start", "stop", "name"}
    for opt in ("frame", "sampling", "overwrite"):
        assert opt in props


def test_transform_tool_registered_gated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_transform")
    assert t.get("gated", False) is True
    props = t["input_schema"]["properties"]
    assert set(t["input_schema"]["required"]) == {"start", "stop", "name"}
    for opt in ("from_frame", "to_frame", "sampling", "overwrite"):
        assert opt in props


def test_ephemeris_handler_delegates_to_fetch_ephemeris(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    import SciQLop.components.agents.tools.orbits as orbits

    captured = {}

    def fake_fetch_ephemeris(body, frame, start, stop, sampling, name, shell_ns, **kw):
        captured.update(body=body, frame=frame, name=name, kw=kw)
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(orbits, "fetch_ephemeris", fake_fetch_ephemeris)
    monkeypatch.setattr(builder, "_kernel_manager",
                        lambda: type("KM", (), {"shell": type("S", (), {"user_ns": {}})()})())

    out = asyncio.run(_tool(qtbot, "sciqlop_ephemeris")["handler"](
        {"body": "Solar Orbiter", "frame": "HEEQ", "start": 0, "stop": 10,
         "name": "orbit", "sampling": 600, "overwrite": True}))
    assert out["content"][0]["text"] == "ok"
    assert captured["body"] == "Solar Orbiter" and captured["frame"] == "HEEQ"
    assert captured["kw"]["overwrite"] is True


def test_ephemeris_handler_errors_without_kernel(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder, "_kernel_manager", lambda: None)
    out = asyncio.run(_tool(qtbot, "sciqlop_ephemeris")["handler"](
        {"body": "Solar Orbiter", "start": 0, "stop": 1, "name": "orbit"}))
    assert "kernel is not available" in out["content"][0]["text"]


def test_transform_handler_delegates_to_fetch_transform(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    import SciQLop.components.agents.tools.orbits as orbits

    captured = {}

    def fake_fetch_transform(from_frame, to_frame, start, stop, sampling, name, shell_ns, **kw):
        captured.update(from_frame=from_frame, to_frame=to_frame, name=name)
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(orbits, "fetch_transform", fake_fetch_transform)
    monkeypatch.setattr(builder, "_kernel_manager",
                        lambda: type("KM", (), {"shell": type("S", (), {"user_ns": {}})()})())

    out = asyncio.run(_tool(qtbot, "sciqlop_transform")["handler"](
        {"from_frame": "GSE", "to_frame": "HEEQ", "start": 0, "stop": 10, "name": "R"}))
    assert out["content"][0]["text"] == "ok"
    assert captured["from_frame"] == "GSE" and captured["to_frame"] == "HEEQ"


def test_transform_handler_errors_without_kernel(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder, "_kernel_manager", lambda: None)
    out = asyncio.run(_tool(qtbot, "sciqlop_transform")["handler"](
        {"start": 0, "stop": 1, "name": "R"}))
    assert "kernel is not available" in out["content"][0]["text"]


def test_bodies_and_frames_handler_delegates_to_cached_call(qtbot, monkeypatch):
    """Monkeypatches the module-level `orbits.bodies_and_frames` (the
    CacheCall-wrapped function from Task 1) directly, rather than exercising
    it through the real disk-persistent cache — same reasoning as
    test_bodies_and_frames_impl_calls_both_endpoints_and_renders in Task 1."""
    import SciQLop.components.agents.tools.orbits as orbits
    monkeypatch.setattr(orbits, "bodies_and_frames", lambda: "### bodies (1)\nEarth")
    out = asyncio.run(_tool(qtbot, "sciqlop_orbit_bodies_and_frames")["handler"]({}))
    assert "Earth" in out["content"][0]["text"]
