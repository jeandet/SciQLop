"""literature.py: arXiv/ADS parsing, token resolution, search orchestration.

Importing the agents package pulls in SciQLopPlots' ProductsModel static, which
needs a QApplication — so each test takes pytest-qt's `qtbot` fixture and imports
the module inside the test (deferred), matching tests/test_install_package_tool.py.
"""

_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v1</id>
    <published>2024-01-02T00:00:00Z</published>
    <title>Reconnection in the magnetotail</title>
    <summary>  We study   reconnection.  </summary>
    <author><name>A. Smith</name></author>
    <author><name>B. Jones</name></author>
    <arxiv:doi>10.1000/xyz</arxiv:doi>
  </entry>
</feed>"""

_ADS_JSON = {"response": {"docs": [
    {"title": ["Solar wind turbulence"], "author": ["Doe, J.", "Roe, R."],
     "year": "2023", "bibcode": "2023ApJ...1..1D", "doi": ["10.1/abc"],
     "abstract": "Turbulence study."}]}}


def _lit(qtbot):
    import SciQLop.components.agents.tools.literature as lit
    return lit


def test_parse_arxiv_atom(qtbot):
    lit = _lit(qtbot)
    papers = lit._parse_arxiv_atom(_ARXIV_XML)
    assert len(papers) == 1
    p = papers[0]
    assert p.title == "Reconnection in the magnetotail"
    assert p.authors == ["A. Smith", "B. Jones"]
    assert p.year == "2024"
    assert p.identifier == "2401.01234v1"
    assert p.venue == "arXiv"
    assert p.doi == "10.1000/xyz"
    assert p.url == "http://arxiv.org/abs/2401.01234v1"
    assert p.abstract == "We study reconnection."


def test_parse_ads_json(qtbot):
    lit = _lit(qtbot)
    papers = lit._parse_ads_json(_ADS_JSON)
    assert len(papers) == 1
    p = papers[0]
    assert p.title == "Solar wind turbulence"
    assert p.authors == ["Doe, J.", "Roe, R."]
    assert p.year == "2023"
    assert p.identifier == "2023ApJ...1..1D"
    assert p.venue == "ADS"
    assert p.doi == "10.1/abc"
    assert "adsabs.harvard.edu/abs/2023ApJ" in p.url


def test_render_paper_contains_fields(qtbot):
    lit = _lit(qtbot)
    p = lit.Paper(title="T", authors=["X"], year="2024", venue="arXiv",
                  identifier="2401.1", doi="10.1/a", url="http://u", abstract="A")
    md = lit._render_paper(p)
    assert "T" in md and "2024" in md and "2401.1" in md and "http://u" in md


def test_ads_token_prefers_settings_then_env(qtbot, monkeypatch):
    lit = _lit(qtbot)

    class _S:
        token = "from-settings"
    monkeypatch.setattr(lit, "AdsCredentialsSettings", lambda: _S())
    monkeypatch.delenv("ADS_API_TOKEN", raising=False)
    assert lit.ads_token() == "from-settings"

    class _Empty:
        token = ""
    monkeypatch.setattr(lit, "AdsCredentialsSettings", lambda: _Empty())
    monkeypatch.setenv("ADS_API_TOKEN", "from-env")
    assert lit.ads_token() == "from-env"


def test_search_literature_arxiv_only(qtbot, monkeypatch):
    lit = _lit(qtbot)
    monkeypatch.setattr(lit, "search_arxiv",
                        lambda q, n: [lit.Paper(title="P", authors=[], year="2024",
                                                venue="arXiv", identifier="2401.1",
                                                doi="", url="http://u", abstract="a")])
    monkeypatch.setattr(lit, "search_ads",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ads called")))
    out = lit.search_literature("recon", source="arxiv", max_results=3)
    text = out["content"][0]["text"]
    assert "2401.1" in text and "P" in text


def test_search_literature_both_without_token_notes_skip(qtbot, monkeypatch):
    lit = _lit(qtbot)
    monkeypatch.setattr(lit, "search_arxiv", lambda q, n: [])
    monkeypatch.setattr(lit, "ads_token", lambda: None)
    out = lit.search_literature("recon", source="both", max_results=3)
    assert "ADS skipped" in out["content"][0]["text"]


def test_search_ads_impl_parses(qtbot, monkeypatch):
    lit = _lit(qtbot)

    class _Resp:
        ok = True
        def json(self):          # speasy Response.json is a method, not a property
            return _ADS_JSON
    monkeypatch.setattr(lit, "ads_token", lambda: "tok")
    monkeypatch.setattr(lit.http, "get", lambda *a, **k: _Resp())
    papers = lit._search_ads_impl("turbulence", 3)
    assert len(papers) == 1
    assert papers[0].identifier == "2023ApJ...1..1D"


def test_search_ads_impl_no_token_returns_empty(qtbot, monkeypatch):
    lit = _lit(qtbot)
    monkeypatch.setattr(lit, "ads_token", lambda: None)
    monkeypatch.setattr(lit.http, "get",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("http called without token")))
    assert lit._search_ads_impl("turbulence", 3) == []


def test_resolve_via_ads_finds_arxiv_id(qtbot, monkeypatch):
    lit = _lit(qtbot)

    class _Resp:
        ok = True
        def json(self):
            return {"response": {"docs": [{"identifier": [
                "2023arXiv230100903R", "2023ApJ...945...28R",
                "10.3847/1538-4357/acaf6c", "10.48550/arXiv.2301.00903",
                "arXiv:2301.00903"]}]}}
    monkeypatch.setattr(lit, "ads_token", lambda: "tok")
    monkeypatch.setattr(lit.http, "get", lambda *a, **k: _Resp())
    assert lit._resolve_via_ads_impl("10.3847/1538-4357/acaf6c", "doi") == "2301.00903"


def test_resolve_via_ads_no_arxiv_entry_returns_none(qtbot, monkeypatch):
    lit = _lit(qtbot)

    class _Resp:
        ok = True
        def json(self):
            return {"response": {"docs": [{"identifier": [
                "2008JGRA..113.7216D", "10.1029/2007JA012998"]}]}}
    monkeypatch.setattr(lit, "ads_token", lambda: "tok")
    monkeypatch.setattr(lit.http, "get", lambda *a, **k: _Resp())
    assert lit._resolve_via_ads_impl("2008JGRA..113.7216D", "bibcode") is None


def test_resolve_via_ads_no_token_returns_none_without_http_call(qtbot, monkeypatch):
    lit = _lit(qtbot)
    monkeypatch.setattr(lit, "ads_token", lambda: None)
    monkeypatch.setattr(lit.http, "get",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("http called without token")))
    assert lit._resolve_via_ads_impl("2008JGRA..113.7216D", "bibcode") is None


def test_resolve_via_ads_no_docs_returns_none(qtbot, monkeypatch):
    lit = _lit(qtbot)

    class _Resp:
        ok = True
        def json(self):
            return {"response": {"docs": []}}
    monkeypatch.setattr(lit, "ads_token", lambda: "tok")
    monkeypatch.setattr(lit.http, "get", lambda *a, **k: _Resp())
    assert lit._resolve_via_ads_impl("nonexistent", "bibcode") is None


def test_resolve_via_ads_builds_correct_query_for_doi_and_bibcode(qtbot, monkeypatch):
    lit = _lit(qtbot)
    calls = []

    class _Resp:
        ok = True
        def json(self):
            return {"response": {"docs": []}}

    def _get(url, headers=None, params=None, timeout=0):
        calls.append(params)
        return _Resp()
    monkeypatch.setattr(lit, "ads_token", lambda: "tok")
    monkeypatch.setattr(lit.http, "get", _get)
    lit._resolve_via_ads_impl("10.3847/1538-4357/acaf6c", "doi")
    lit._resolve_via_ads_impl("2023ApJ...945...28R", "bibcode")
    assert calls[0]["q"] == 'doi:"10.3847/1538-4357/acaf6c"'
    assert calls[1]["q"] == "bibcode:2023ApJ...945...28R"
