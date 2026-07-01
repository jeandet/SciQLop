"""sciqlop_fetch registration + handler wiring (needs QApplication → qtbot)."""
import asyncio
from unittest.mock import MagicMock


def _tool(qtbot, name):
    import SciQLop.components.agents.tools._builder as builder
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_fetch_tool_registered_gated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_fetch")
    assert t.get("gated", False) is True
    props = t["input_schema"]["properties"]
    assert props["products"]["type"] == "array"
    assert set(t["input_schema"]["required"]) == {"products", "start", "stop", "name"}
    for opt in ("cadence", "overwrite", "preview"):
        assert opt in props


def test_fetch_handler_delegates_to_fetch_products(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    import SciQLop.components.agents.tools.fetch as fetch

    captured = {}

    def fake_fetch_products(products, start, stop, name, shell_ns, **kw):
        captured.update(products=products, name=name, kw=kw)
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(fetch, "fetch_products", fake_fetch_products)
    monkeypatch.setattr(builder, "_kernel_manager",
                        lambda: type("KM", (), {"shell": type("S", (), {"user_ns": {}})()})())

    out = asyncio.run(_tool(qtbot, "sciqlop_fetch")["handler"](
        {"products": ["speasy//amda//x"], "start": 0, "stop": 10, "name": "V",
         "cadence": "1min", "overwrite": True, "preview": False}))
    assert out["content"][0]["text"] == "ok"
    assert captured["name"] == "V" and captured["kw"]["cadence"] == "1min"


def test_fetch_handler_errors_without_kernel(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder, "_kernel_manager", lambda: None)
    out = asyncio.run(_tool(qtbot, "sciqlop_fetch")["handler"](
        {"products": ["x"], "start": 0, "stop": 1, "name": "V"}))
    assert "kernel is not available" in out["content"][0]["text"]
