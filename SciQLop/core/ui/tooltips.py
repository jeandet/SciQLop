from html import escape

__all__ = ["rich_tooltip"]


def rich_tooltip(title: str, body: str = "", shortcut: str = "") -> str:
    """Format a Qt rich-text tooltip: bold title, optional shortcut and body.

    Qt auto-detects HTML in tooltips, so returning tags is sufficient. Inputs
    are HTML-escaped defensively (static literals today, but cheap insurance
    against accidental markup breakage).
    """
    html = f"<b>{escape(title)}</b>"
    if shortcut:
        html += f' <span style="color:gray">({escape(shortcut)})</span>'
    if body:
        html += f"<br>{escape(body)}"
    return html
