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


def test_classify_identifier_arxiv_doi_bibcode(qtbot):
    ft = _ft(qtbot)
    assert ft._classify_identifier("2401.01234") == "arxiv"
    assert ft._classify_identifier("https://arxiv.org/abs/2401.01234") == "arxiv"
    assert ft._classify_identifier("astro-ph/0601001") == "arxiv"
    assert ft._classify_identifier("10.3847/1538-4357/acaf6c") == "doi"
    assert ft._classify_identifier("10.1029/2007JA012998") == "doi"
    assert ft._classify_identifier("2023ApJ...945...28R") == "bibcode"
    assert ft._classify_identifier("2008JGRA..113.7216D") == "bibcode"


def test_fetch_paper_doi_resolves_via_ads_to_arxiv(qtbot, monkeypatch):
    ft = _ft(qtbot)
    monkeypatch.setattr(ft.literature, "ads_token", lambda: "tok")
    monkeypatch.setattr(ft.literature, "resolve_via_ads", lambda ident, kind: "2401.01234")
    body = "<html><body><p>" + ("Full body text. " * 50) + "</p></body></html>"
    monkeypatch.setattr(ft.http, "get", lambda url, timeout=0: _Resp(text=body, ctype="text/html"))
    out = ft._fetch_paper_impl("10.3847/1538-4357/acaf6c")
    assert "Full body text." in out["content"][0]["text"]


def test_fetch_paper_bibcode_no_open_access_reports_cleanly(qtbot, monkeypatch):
    ft = _ft(qtbot)
    monkeypatch.setattr(ft.literature, "ads_token", lambda: "tok")
    monkeypatch.setattr(ft.literature, "resolve_via_ads", lambda ident, kind: None)
    monkeypatch.setattr(ft.http, "get",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no publisher scraping")))
    out = ft._fetch_paper_impl("2008JGRA..113.7216D")
    text = out["content"][0]["text"].lower()
    assert "no open-access full text" in text


def test_fetch_paper_doi_without_ads_token_reports_clearly(qtbot, monkeypatch):
    ft = _ft(qtbot)
    monkeypatch.setattr(ft.literature, "ads_token", lambda: None)
    monkeypatch.setattr(ft.literature, "resolve_via_ads",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ADS called without token")))
    out = ft._fetch_paper_impl("10.3847/1538-4357/acaf6c")
    assert "ads token required" in out["content"][0]["text"].lower()


def test_fetch_paper_garbage_without_ads_token_reports_clearly(qtbot, monkeypatch):
    ft = _ft(qtbot)
    monkeypatch.setattr(ft.literature, "ads_token", lambda: None)
    out = ft._fetch_paper_impl("garbage")
    assert "ads token required" in out["content"][0]["text"].lower()
