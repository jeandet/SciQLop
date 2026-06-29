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
