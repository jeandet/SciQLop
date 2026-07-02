"""sciqlop_describe_product registration + handler wiring (needs QApplication → qtbot)."""
from unittest.mock import MagicMock


def _tool(qtbot, name):
    import SciQLop.components.agents.tools._builder as builder
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_describe_tool_registered_ungated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_describe_product")
    assert t.get("gated", False) is False
    props = t["input_schema"]["properties"]
    assert props["product"]["type"] == "string"
    assert set(t["input_schema"]["required"]) == {"product"}
    for opt in ("probe", "start", "stop"):
        assert opt in props


def test_describe_handler_delegates(qtbot, monkeypatch):
    import asyncio
    import SciQLop.components.agents.tools.describe as describe
    captured = {}

    def fake_describe_product(product, *, probe, start, stop, resolve_index, probe_fetch):
        captured.update(product=product, probe=probe)
        return {"content": [{"type": "text", "text": "ok"}]}

    monkeypatch.setattr(describe, "describe_product", fake_describe_product)
    out = asyncio.run(_tool(qtbot, "sciqlop_describe_product")["handler"](
        {"product": "cda/AC_H2_CRIS/cnt_Al", "probe": True}))
    assert out["content"][0]["text"] == "ok"
    assert captured["product"] == "cda/AC_H2_CRIS/cnt_Al" and captured["probe"] is True


def test_resolve_index_routes_speasy_uid(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    fake_index = object()

    class _Prov:
        parameters = {"AC_H2_CRIS/cnt_Al": fake_index}

    class _Flat:
        cda = _Prov()

    import speasy as spz
    monkeypatch.setattr(spz.inventories, "flat_inventories", _Flat(), raising=False)
    resolve = builder._make_resolve_index()
    index, note = resolve("cda/AC_H2_CRIS/cnt_Al")
    assert index is fake_index and note is None
