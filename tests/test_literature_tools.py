"""sciqlop_search_literature / sciqlop_fetch_paper tool registration.

Importing _builder needs a QApplication (ProductsModel static), so each test
takes pytest-qt's `qtbot` and imports inside (deferred), matching
tests/test_install_package_tool.py.
"""
import asyncio
from unittest.mock import MagicMock


def _tool(qtbot, name):
    import SciQLop.components.agents.tools._builder as builder
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_search_tool_registered_ungated_with_schema(qtbot):
    t = _tool(qtbot, "sciqlop_search_literature")
    assert t.get("gated", False) is False
    props = t["input_schema"]["properties"]
    assert props["query"]["type"] == "string"
    assert props["source"]["enum"] == ["arxiv", "ads", "both"]
    assert t["input_schema"]["required"] == ["query"]


def test_fetch_tool_registered(qtbot):
    t = _tool(qtbot, "sciqlop_fetch_paper")
    assert t.get("gated", False) is False
    assert t["input_schema"]["required"] == ["id_or_url"]


def test_search_tool_handler_delegates(qtbot, monkeypatch):
    import SciQLop.components.agents.tools.literature as lit
    monkeypatch.setattr(lit, "search_literature",
                        lambda q, s, n: {"content": [{"type": "text", "text": f"q={q} s={s} n={n}"}]})
    out = asyncio.run(_tool(qtbot, "sciqlop_search_literature")["handler"]({"query": "recon", "source": "arxiv", "max_results": 3}))
    assert out["content"][0]["text"] == "q=recon s=arxiv n=3"
