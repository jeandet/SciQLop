"""fulltext.py: arXiv id extraction, HTML→text, PDF→text, fetch orchestration.

Importing the agents package needs a QApplication (ProductsModel static), so each
test takes pytest-qt's `qtbot` and imports the module inside (deferred), matching
tests/test_install_package_tool.py.
"""


class _Resp:
    def __init__(self, ok=True, text="", data=b"", ctype="text/html"):
        self.ok = ok
        self.text = text
        self.bytes = data
        self.headers = {"Content-Type": ctype}


def _ft(qtbot):
    import SciQLop.components.agents.tools.fulltext as ft
    return ft


def test_extract_arxiv_id_from_url_and_bare(qtbot):
    ft = _ft(qtbot)
    assert ft._extract_arxiv_id("https://arxiv.org/abs/2401.01234v2") == "2401.01234v2"
    assert ft._extract_arxiv_id("2401.01234") == "2401.01234"
    assert ft._extract_arxiv_id("astro-ph/0601001") == "astro-ph/0601001"
    assert ft._extract_arxiv_id("not an id") == ""


def test_html_to_text_strips_markup_and_scripts(qtbot):
    ft = _ft(qtbot)
    html = "<html><head><style>x{}</style></head><body><p>Hello</p><script>bad()</script><p>world</p></body></html>"
    assert ft._html_to_text(html) == "Hello world"


def test_fetch_paper_uses_html(qtbot, monkeypatch):
    ft = _ft(qtbot)
    body = "<html><body><p>" + ("Full body text. " * 50) + "</p></body></html>"
    monkeypatch.setattr(ft.http, "get", lambda url, timeout=0: _Resp(text=body, ctype="text/html"))
    out = ft._fetch_paper_impl("2401.01234")
    assert "Full body text." in out["content"][0]["text"]


def test_fetch_paper_pdf_fallback(qtbot, monkeypatch):
    ft = _ft(qtbot)

    def _get(url, timeout=0):
        if "/pdf/" in url:
            return _Resp(ok=True, data=b"%PDF-fake", ctype="application/pdf")
        return _Resp(ok=False, ctype="text/plain")  # HTML attempts fail
    monkeypatch.setattr(ft.http, "get", _get)
    monkeypatch.setattr(ft, "_pdf_to_text", lambda data: "Extracted PDF text body.")
    out = ft._fetch_paper_impl("2401.01234")
    assert "Extracted PDF text body." in out["content"][0]["text"]


def test_fetch_paper_unresolvable(qtbot):
    ft = _ft(qtbot)
    out = ft._fetch_paper_impl("garbage")
    assert "could not resolve" in out["content"][0]["text"].lower()
