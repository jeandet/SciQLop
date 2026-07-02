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


class _FakeVar:
    name = "v"

    def replace_fillval_by_nan(self, inplace=True, convert_to_float=True):
        return self


def _run_fetch_one(qtbot, monkeypatch, product_id, ns=None):
    """Drive the real (non-injected) `_fetch_one` closure through the full
    sciqlop_fetch handler, to exercise its `//`-vs-uid routing and
    list-normalisation without duplicating that logic in a test double."""
    import SciQLop.components.agents.tools._builder as builder
    ns = {} if ns is None else ns
    monkeypatch.setattr(builder, "_kernel_manager",
                        lambda: type("KM", (), {"shell": type("S", (), {"user_ns": ns})()})())
    asyncio.run(_tool(qtbot, "sciqlop_fetch")["handler"](
        {"products": [product_id], "start": 0, "stop": 10, "name": "V"}))
    return ns


def test_fetch_one_routes_slash_path_to_dependency_resolver(qtbot, monkeypatch):
    from SciQLop.components.plotting.backend import dependencies
    calls = {}
    monkeypatch.setattr(dependencies, "resolve_product_path",
                        lambda pid, t0, t1: calls.setdefault("path", (pid, t0, t1)) or _FakeVar())
    monkeypatch.setattr("speasy.get_data",
                        lambda *a: (_ for _ in ()).throw(AssertionError("speasy.get_data called for a //-path")))
    _run_fetch_one(qtbot, monkeypatch, "speasy//amda//x")
    assert calls["path"] == ("speasy//amda//x", 0.0, 10.0)


def test_fetch_one_routes_bare_uid_to_speasy(qtbot, monkeypatch):
    from SciQLop.components.plotting.backend import dependencies
    calls = {}
    monkeypatch.setattr(dependencies, "resolve_product_path",
                        lambda *a: (_ for _ in ()).throw(AssertionError("resolve_product_path called for a bare uid")))
    monkeypatch.setattr("speasy.get_data",
                        lambda pid, t0, t1: calls.setdefault("uid", (pid, t0, t1)) or _FakeVar())
    _run_fetch_one(qtbot, monkeypatch, "amda/imf_gsm")
    assert calls["uid"] == ("amda/imf_gsm", 0.0, 10.0)


def test_fetch_one_normalizes_single_object_to_one_entry(qtbot, monkeypatch):
    from SciQLop.components.plotting.backend import dependencies
    monkeypatch.setattr(dependencies, "resolve_product_path", lambda *a: _FakeVar())
    ns = _run_fetch_one(qtbot, monkeypatch, "speasy//amda//x")
    assert len(ns["V"]) == 1


def test_fetch_one_passes_through_list_of_vars(qtbot, monkeypatch):
    from SciQLop.components.plotting.backend import dependencies
    var_a, var_b = _FakeVar(), _FakeVar()
    var_a.name, var_b.name = "a", "b"
    monkeypatch.setattr(dependencies, "resolve_product_path", lambda *a: [var_a, var_b])
    ns = _run_fetch_one(qtbot, monkeypatch, "speasy//amda//x")
    assert set(ns["V"].keys()) == {"a", "b"}


def test_fetch_one_raises_on_falsy_data(qtbot, monkeypatch):
    from SciQLop.components.plotting.backend import dependencies
    monkeypatch.setattr(dependencies, "resolve_product_path", lambda *a: None)
    ns = _run_fetch_one(qtbot, monkeypatch, "speasy//amda//x")
    assert "V" not in ns
