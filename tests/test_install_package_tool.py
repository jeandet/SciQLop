"""sciqlop_install_package: gated tool that delegates to install_packages."""
import asyncio
from unittest.mock import MagicMock


def _get_tool(qtbot):
    from SciQLop.components.agents.tools._builder import build_sciqlop_tools
    tools = build_sciqlop_tools(MagicMock())
    return next(t for t in tools if t["name"] == "sciqlop_install_package")


def test_tool_is_registered_and_gated(qtbot):
    tool = _get_tool(qtbot)
    assert tool["gated"] is True
    assert tool["input_schema"]["properties"]["packages"]["type"] == "array"
    assert tool["input_schema"]["required"] == ["packages"]


def test_tool_handler_delegates(qtbot, monkeypatch):
    import SciQLop.user_api.packages as pkgs
    monkeypatch.setattr(pkgs, "install_packages",
                        lambda *s: {"ok": True, "installed": list(s),
                                    "already_present": [], "error": ""})
    tool = _get_tool(qtbot)
    out = asyncio.run(tool["handler"]({"packages": ["astropy"]}))
    text = out["content"][0]["text"]
    assert "astropy" in text
