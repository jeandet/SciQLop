"""Local-origin web pages must be allowed to load remote images.

The appstore and welcome pages are rendered with ``setHtml(html, base_url)``
where ``base_url`` is a ``file://`` URL, so their document origin is local.
Plugin card thumbnails and screenshots are remote ``https://`` URLs. QtWebEngine
blocks a local-origin document from loading remote URLs unless
``LocalContentCanAccessRemoteUrls`` is enabled — without it every card falls
back to the emoji placeholder and the screenshot carousel stays empty.
"""
from PySide6.QtWebEngineCore import QWebEngineSettings
from SciQLop.components.appstore.web_appstore_page import AppStorePage


def test_local_page_can_load_remote_images(qapp):
    page = AppStorePage()
    settings = page._view.settings()
    assert settings.testAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls), \
        "remote plugin images won't load from the file:// origin without this"
