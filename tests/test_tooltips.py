from SciQLop.core.ui.tooltips import rich_tooltip


def test_title_only():
    assert rich_tooltip("New plot panel") == "<b>New plot panel</b>"


def test_title_and_body():
    assert rich_tooltip("New plot panel", "Create an empty panel.") == (
        "<b>New plot panel</b><br>Create an empty panel."
    )


def test_title_with_shortcut():
    assert rich_tooltip("Crosshair", shortcut="Ctrl+Shift+H") == (
        '<b>Crosshair</b> <span style="color:gray">(Ctrl+Shift+H)</span>'
    )


def test_title_body_and_shortcut():
    assert rich_tooltip("Crosshair", "Toggle crosshair.", "Ctrl+Shift+H") == (
        '<b>Crosshair</b> <span style="color:gray">(Ctrl+Shift+H)</span>'
        "<br>Toggle crosshair."
    )


def test_escapes_html_metacharacters():
    assert rich_tooltip("A & B", "x < y > z") == (
        "<b>A &amp; B</b><br>x &lt; y &gt; z"
    )
