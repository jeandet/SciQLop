import asyncio
from unittest.mock import MagicMock


def test_current_figure_png_none_when_no_figure(qtbot):
    import matplotlib.pyplot as plt
    from SciQLop.components.agents.tools.figure import current_figure_png
    plt.close("all")
    assert current_figure_png() is None


def test_current_figure_png_returns_bytes_when_present(qtbot):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from SciQLop.components.agents.tools.figure import current_figure_png
    plt.close("all")
    plt.figure(); plt.plot([0, 1, 2], [3, 1, 2])
    png = current_figure_png()
    plt.close("all")
    assert isinstance(png, (bytes, bytearray)) and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_show_figure_tool_registered_ungated(qtbot):
    import SciQLop.components.agents.tools._builder as builder
    t = next(x for x in builder.build_sciqlop_tools(MagicMock()) if x["name"] == "sciqlop_show_figure")
    assert t.get("gated", False) is False


def test_show_figure_handler_reports_when_no_figure(qtbot, monkeypatch):
    import matplotlib.pyplot as plt
    plt.close("all")
    import SciQLop.components.agents.tools._builder as builder
    t = next(x for x in builder.build_sciqlop_tools(MagicMock()) if x["name"] == "sciqlop_show_figure")
    out = asyncio.run(t["handler"]({}))
    assert "no active matplotlib figure" in out["content"][0]["text"].lower()
