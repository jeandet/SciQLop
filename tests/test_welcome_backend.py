from PySide6.QtCore import QSize
from SciQLop.components.welcome.backend import _icon_to_data_uri


def _distinct_colors(icon):
    px = icon.pixmap(QSize(80, 80))
    if px.isNull():
        return 0
    img = px.toImage()
    return len({img.pixelColor(x, y).rgba() for x in range(0, 80, 8) for y in range(0, 80, 8)})


def test_plot_panel_quickstart_icon_renders_non_blank(qapp):
    import SciQLop.resources  # noqa: F401
    from SciQLop.components.theming import theme_icon
    icon = theme_icon("add_graph")
    assert _distinct_colors(icon) > 1, "plot-panel icon must not be a uniform/blank square"
    uri = _icon_to_data_uri(icon)
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > len("data:image/png;base64,")
