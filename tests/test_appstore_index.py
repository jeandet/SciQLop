"""The appstore index pass-through must preserve optional media fields.

`image` and `screenshots` are optional URL fields the client renders (card
thumbnail + screenshot carousel). `_filter_packages` only narrows `versions`;
it must keep every other key so the JS can read these. This guards against a
future refactor that whitelists keys and silently drops media.
"""
from SciQLop.components.appstore.backend import _filter_packages


def _entry(**extra):
    base = {
        "name": "Demo",
        "type": "plugin",
        "versions": [{"version": "1.0.0", "sciqlop": ""}],
    }
    base.update(extra)
    return base


def test_image_and_screenshots_preserved():
    pkg = _entry(
        image="https://example.com/card.png",
        screenshots=["https://example.com/01.png", "https://example.com/02.png"],
    )
    out = _filter_packages([pkg])
    assert len(out) == 1
    assert out[0]["image"] == "https://example.com/card.png"
    assert out[0]["screenshots"] == ["https://example.com/01.png", "https://example.com/02.png"]


def test_missing_media_fields_are_simply_absent():
    out = _filter_packages([_entry()])
    assert len(out) == 1
    assert "image" not in out[0]
    assert "screenshots" not in out[0]
