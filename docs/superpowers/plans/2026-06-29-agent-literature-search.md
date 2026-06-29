# Agent Literature Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give all three agents real literature access — arXiv + NASA ADS search and arXiv full-text (HTML→PDF) as ungated tools — plus Claude's built-in web tools.

**Architecture:** Two pure-logic modules (`literature.py`, `fulltext.py`) do parsing; HTTP goes through `speasy.core.http.get` and results are disk-cached with `speasy.core.cache.CacheCall`. Two ungated `thread=True` read tools expose them. ADS token lives in the OS keyring via a `ConfigEntry` + `KeyringMapping`. Claude gets `WebSearch`/`WebFetch` via `allowed_tools` (plugins repo).

**Tech Stack:** Python, `speasy.core.http`/`speasy.core.cache`, stdlib `xml.etree`/`html.parser`, `pypdf`, pydantic settings, pytest.

## Global Constraints

- All HTTP via `speasy.core.http.get(url, headers=?, params=?, timeout=?) -> Response`. `Response` exposes properties `.ok`, `.status_code`, `.text`, `.bytes`, `.json`, `.headers`, `.url` (no parentheses).
- Cache with `from speasy.core.cache import CacheCall` → `@CacheCall(cache_retention=<seconds>, is_pure=False)`.
- Tools are **ungated** read tools built with `_text_tool(..., thread=True)`; handlers return the `{"content": [...]}` shape (the wrapper coerces non-dict returns).
- ADS token: `AdsCredentialsSettings` `ConfigEntry` with `_keyring_ = KeyringMapping("service","username","token")`; `token` is `widget:"password"` (keyring-stored, never in YAML). `ads_token()` returns it, else `ADS_API_TOKEN` env.
- New dependencies: `pypdf` and `defusedxml` (no `httpx`). Parse XML with
  `defusedxml.ElementTree` — never stdlib `xml.etree` (XXE / billion-laughs).
- SciQLop test command: `uv run pytest --no-xvfb <path> -v` (run from the SciQLop repo root, branch `feat/agent-literature-search`). Stage only the files each task lists — never `git add -A` (untracked build dirs exist).
- Tasks 1–3 are SciQLop; Task 4 is the plugins repo.

---

## File Structure

- `SciQLop/components/agents/tools/literature.py` — new: `Paper`, arXiv/ADS parsers, `search_arxiv`/`search_ads` (http+cache), `ads_token`, `search_literature`, `_render_paper`.
- `SciQLop/components/agents/settings.py` — add `AdsCredentialsSettings`.
- `SciQLop/components/agents/tools/fulltext.py` — new: `fetch_paper` + pure helpers.
- `SciQLop/components/agents/tools/_builder.py` — register two tools.
- `pyproject.toml` — add `pypdf`.
- `sciqlop_claude/.../backend.py` (+opencode/copilot) — Claude web tools + prompt mentions (plugins repo).
- Tests: `tests/test_literature.py`, `tests/test_fulltext.py`, `tests/test_literature_tools.py` (SciQLop); a Claude test in the plugins repo.

---

### Task 1: Literature search module + ADS token settings

**Files:**
- Create: `SciQLop/components/agents/tools/literature.py`
- Modify: `SciQLop/components/agents/settings.py`
- Modify: `pyproject.toml` (add `defusedxml`)
- Test: `tests/test_literature.py`

**Interfaces — Produces:**
- `Paper` dataclass: `title:str, authors:list[str], year:str, venue:str, identifier:str, doi:str, url:str, abstract:str`.
- `search_arxiv(query:str, max_results:int) -> list[Paper]`, `search_ads(query:str, max_results:int, token:str) -> list[Paper]`.
- `ads_token() -> Optional[str]`.
- `search_literature(query:str, source:str="both", max_results:int=5) -> dict` (`{"content":[{"type":"text","text":...}]}`).
- `AdsCredentialsSettings` (ConfigEntry) with field `token`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_literature.py`:

```python
"""literature.py: arXiv/ADS parsing, token resolution, search orchestration."""
import SciQLop.components.agents.tools.literature as lit
from SciQLop.components.agents.tools.literature import Paper

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


def test_parse_arxiv_atom():
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


def test_parse_ads_json():
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


def test_render_paper_contains_fields():
    p = Paper(title="T", authors=["X"], year="2024", venue="arXiv",
              identifier="2401.1", doi="10.1/a", url="http://u", abstract="A")
    md = lit._render_paper(p)
    assert "T" in md and "2024" in md and "2401.1" in md and "http://u" in md


def test_ads_token_prefers_settings_then_env(monkeypatch):
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


def test_search_literature_arxiv_only(monkeypatch):
    monkeypatch.setattr(lit, "search_arxiv",
                        lambda q, n: [Paper(title="P", authors=[], year="2024",
                                            venue="arXiv", identifier="2401.1",
                                            doi="", url="http://u", abstract="a")])
    monkeypatch.setattr(lit, "search_ads", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ads called")))
    out = lit.search_literature("recon", source="arxiv", max_results=3)
    text = out["content"][0]["text"]
    assert "2401.1" in text and "P" in text


def test_search_literature_both_without_token_notes_skip(monkeypatch):
    monkeypatch.setattr(lit, "search_arxiv", lambda q, n: [])
    monkeypatch.setattr(lit, "ads_token", lambda: None)
    out = lit.search_literature("recon", source="both", max_results=3)
    assert "ADS skipped" in out["content"][0]["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_literature.py -v`
Expected: FAIL — `ModuleNotFoundError: ...tools.literature`.

- [ ] **Step 3: Add `AdsCredentialsSettings` to `settings.py`**

In `SciQLop/components/agents/settings.py`, add after the existing imports/class:

```python
from pydantic import Field  # if not already imported
from SciQLop.components.settings.backend.entry import KeyringMapping


class AdsCredentialsSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Agent chat"
    _keyring_ = KeyringMapping("service", "username", "token")
    service: str = Field(default="nasa-ads", json_schema_extra={"widget": "hidden"})
    username: str = Field(default="ads_api_token", json_schema_extra={"widget": "hidden"})
    token: str = Field(
        default="",
        description="NASA ADS API token (https://ui.adsabs.harvard.edu/user/settings/token)",
        json_schema_extra={"widget": "password"},
    )
```

(`ConfigEntry`, `SettingsCategory`, `ClassVar`, `Field` are already imported at the top of `settings.py`; add any that are missing.)

- [ ] **Step 4: Create `literature.py`**

Create `SciQLop/components/agents/tools/literature.py`:

```python
"""arXiv + NASA ADS literature search for the SciQLop agents."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from defusedxml import ElementTree as ET  # XXE / billion-laughs-safe XML parsing

from speasy.core import http
from speasy.core.cache import CacheCall

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_SEARCH_RETENTION = 21600  # 6 h


@dataclass
class Paper:
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: str = ""
    venue: str = ""
    identifier: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""


def _norm(s: str) -> str:
    return " ".join((s or "").split())


def _parse_arxiv_atom(xml_text: str) -> List[Paper]:
    root = ET.fromstring(xml_text)
    papers: List[Paper] = []
    for entry in root.findall(f"{_ATOM}entry"):
        abs_url = _norm(entry.findtext(f"{_ATOM}id") or "")
        arxiv_id = abs_url.split("/abs/", 1)[-1] if "/abs/" in abs_url else abs_url.rsplit("/", 1)[-1]
        papers.append(Paper(
            title=_norm(entry.findtext(f"{_ATOM}title") or ""),
            authors=[_norm(a.findtext(f"{_ATOM}name") or "")
                     for a in entry.findall(f"{_ATOM}author")
                     if _norm(a.findtext(f"{_ATOM}name") or "")],
            year=(entry.findtext(f"{_ATOM}published") or "")[:4],
            venue="arXiv",
            identifier=arxiv_id,
            doi=_norm(entry.findtext(f"{_ARXIV}doi") or ""),
            url=abs_url,
            abstract=_norm(entry.findtext(f"{_ATOM}summary") or ""),
        ))
    return papers


def _parse_ads_json(payload: dict) -> List[Paper]:
    docs = (payload.get("response") or {}).get("docs") or []
    papers: List[Paper] = []
    for d in docs:
        bibcode = d.get("bibcode") or ""
        papers.append(Paper(
            title=_norm((d.get("title") or [""])[0]),
            authors=list(d.get("author") or []),
            year=str(d.get("year") or ""),
            venue="ADS",
            identifier=bibcode,
            doi=(d.get("doi") or [""])[0],
            url=f"https://ui.adsabs.harvard.edu/abs/{bibcode}" if bibcode else "",
            abstract=_norm(d.get("abstract") or ""),
        ))
    return papers


@CacheCall(cache_retention=_SEARCH_RETENTION, is_pure=False)
def search_arxiv(query: str, max_results: int) -> List[Paper]:
    sq = query if ":" in query else f"all:{query}"
    r = http.get("http://export.arxiv.org/api/query",
                 params={"search_query": sq, "max_results": str(max_results)}, timeout=30)
    return _parse_arxiv_atom(r.text) if r.ok else []


@CacheCall(cache_retention=_SEARCH_RETENTION, is_pure=False)
def search_ads(query: str, max_results: int, token: str) -> List[Paper]:
    r = http.get("https://api.adsabs.harvard.edu/v1/search/query",
                 headers={"Authorization": f"Bearer {token}"},
                 params={"q": query, "rows": str(max_results),
                         "fl": "title,author,year,bibcode,doi,abstract"}, timeout=30)
    return _parse_ads_json(r.json) if r.ok else []


def ads_token() -> Optional[str]:
    try:
        from SciQLop.components.agents.settings import AdsCredentialsSettings
        tok = AdsCredentialsSettings().token
        if tok:
            return tok
    except Exception:
        pass
    return os.environ.get("ADS_API_TOKEN") or None


def _render_paper(p: Paper) -> str:
    authors = ", ".join(p.authors[:6]) + (" et al." if len(p.authors) > 6 else "")
    ident = p.identifier + (f" · doi:{p.doi}" if p.doi else "")
    abstract = p.abstract[:300] + ("…" if len(p.abstract) > 300 else "")
    return f"**{p.title}** ({p.year}, {p.venue})\n{authors}\n{ident} · {p.url}\n{abstract}"


def search_literature(query: str, source: str = "both", max_results: int = 5) -> dict:
    src = (source or "both").lower()
    papers: List[Paper] = []
    notes: List[str] = []
    if src in ("arxiv", "both"):
        try:
            papers += search_arxiv(query, max_results)
        except Exception as e:  # noqa: BLE001
            notes.append(f"(arXiv error: {e})")
    if src in ("ads", "both"):
        tok = ads_token()
        if tok:
            try:
                papers += search_ads(query, max_results, tok)
            except Exception as e:  # noqa: BLE001
                notes.append(f"(ADS error: {e})")
        else:
            notes.append("(ADS skipped: no token — set ADS_API_TOKEN or the ADS token in settings)")
    if not papers:
        body = "No results." + ((" " + " ".join(notes)) if notes else "")
        return {"content": [{"type": "text", "text": body}]}
    md = "\n\n".join(_render_paper(p) for p in papers)
    if notes:
        md += "\n\n" + " ".join(notes)
    return {"content": [{"type": "text", "text": md}]}
```

Also add `"defusedxml"` to the `[project] dependencies` list in `pyproject.toml`
(it is already installed transitively; this makes the XML-parser dependency
explicit). `uv pip install defusedxml` if needed.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_literature.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/tools/literature.py SciQLop/components/agents/settings.py pyproject.toml tests/test_literature.py
git commit -m "feat(agents): arXiv + ADS literature search (speasy http + cache)

Pure Atom/JSON parsers, speasy.core.http + CacheCall, ADS token from a
keyring-backed settings entry or ADS_API_TOKEN env.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Full-text fetch (HTML → PDF) + pypdf dependency

**Files:**
- Create: `SciQLop/components/agents/tools/fulltext.py`
- Modify: `pyproject.toml`
- Test: `tests/test_fulltext.py`

**Interfaces — Produces:** `fetch_paper(id_or_url:str) -> dict` (`{"content":[{"type":"text","text":...}]}`); pure helpers `_extract_arxiv_id`, `_html_to_text`, `_pdf_to_text`, `_fetch_paper_impl`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fulltext.py`:

```python
"""fulltext.py: arXiv id extraction, HTML→text, PDF→text, fetch orchestration."""
import SciQLop.components.agents.tools.fulltext as ft


def test_extract_arxiv_id_from_url_and_bare():
    assert ft._extract_arxiv_id("https://arxiv.org/abs/2401.01234v2") == "2401.01234v2"
    assert ft._extract_arxiv_id("2401.01234") == "2401.01234"
    assert ft._extract_arxiv_id("astro-ph/0601001") == "astro-ph/0601001"
    assert ft._extract_arxiv_id("not an id") == ""


def test_html_to_text_strips_markup_and_scripts():
    html = "<html><head><style>x{}</style></head><body><p>Hello</p><script>bad()</script><p>world</p></body></html>"
    assert ft._html_to_text(html) == "Hello world"


class _Resp:
    def __init__(self, ok=True, text="", data=b"", ctype="text/html"):
        self.ok = ok
        self.text = text
        self.bytes = data
        self.headers = {"Content-Type": ctype}


def test_fetch_paper_uses_html(monkeypatch):
    body = "<html><body><p>" + ("Full body text. " * 50) + "</p></body></html>"
    monkeypatch.setattr(ft.http, "get", lambda url, timeout=0: _Resp(text=body, ctype="text/html"))
    out = ft._fetch_paper_impl("2401.01234")
    assert "Full body text." in out["content"][0]["text"]


def test_fetch_paper_pdf_fallback(monkeypatch):
    def _get(url, timeout=0):
        if "/pdf/" in url:
            return _Resp(ok=True, data=b"%PDF-fake", ctype="application/pdf")
        return _Resp(ok=False, ctype="text/plain")  # HTML attempts fail
    monkeypatch.setattr(ft.http, "get", _get)
    monkeypatch.setattr(ft, "_pdf_to_text", lambda data: "Extracted PDF text body.")
    out = ft._fetch_paper_impl("2401.01234")
    assert "Extracted PDF text body." in out["content"][0]["text"]


def test_fetch_paper_unresolvable():
    out = ft._fetch_paper_impl("garbage")
    assert "could not resolve" in out["content"][0]["text"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_fulltext.py -v`
Expected: FAIL — `ModuleNotFoundError: ...tools.fulltext`.

- [ ] **Step 3: Add `pypdf` to `pyproject.toml`**

In `pyproject.toml`, add `"pypdf"` to the `[project] dependencies` list (alongside `"keyring"` etc.). Then install it:
```
uv pip install pypdf
```

- [ ] **Step 4: Create `fulltext.py`**

Create `SciQLop/components/agents/tools/fulltext.py`:

```python
"""Fetch the full text of an arXiv paper (HTML, falling back to PDF)."""
from __future__ import annotations

import io
import re
from html.parser import HTMLParser

from speasy.core import http
from speasy.core.cache import CacheCall

_FETCH_RETENTION = 604800  # 7 d — a published paper is immutable
_MAX_CHARS = 40000
_ARXIV_ID = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?", re.I)


def _msg(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _capped(text: str) -> dict:
    text = text.strip()
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n\n(truncated — ask for a specific section)"
    return _msg(text)


def _extract_arxiv_id(s: str) -> str:
    m = _ARXIV_ID.search((s or "").strip())
    return m.group(0) if m else ""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _html_to_text(html_text: str) -> str:
    p = _TextExtractor()
    p.feed(html_text)
    return " ".join(" ".join(p.parts).split())


def _pdf_to_text(data: bytes) -> str:
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _fetch_paper_impl(id_or_url: str) -> dict:
    arxiv_id = _extract_arxiv_id(id_or_url)
    if not arxiv_id:
        return _msg(f"could not resolve an arXiv id from {id_or_url!r}")
    for url in (f"https://arxiv.org/html/{arxiv_id}", f"https://ar5iv.org/abs/{arxiv_id}"):
        try:
            r = http.get(url, timeout=45)
        except Exception:
            continue
        if r.ok and "html" in str(r.headers.get("Content-Type", "")).lower():
            text = _html_to_text(r.text)
            if len(text) > 500:
                return _capped(text)
    try:
        r = http.get(f"https://arxiv.org/pdf/{arxiv_id}", timeout=60)
        if r.ok:
            text = _pdf_to_text(r.bytes)
            if text.strip():
                return _capped(text)
    except Exception:
        pass
    return _msg(f"could not retrieve full text for {arxiv_id}; use the abstract/DOI instead")


fetch_paper = CacheCall(cache_retention=_FETCH_RETENTION, is_pure=False)(_fetch_paper_impl)
```

`pypdf` was added to `pyproject.toml` in Step 3; `defusedxml` is added in Task 1.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_fulltext.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/tools/fulltext.py pyproject.toml tests/test_fulltext.py
git commit -m "feat(agents): arXiv full-text fetch (HTML via ar5iv, PDF fallback)

fetch_paper resolves an arXiv id, returns cleaned HTML text or pypdf-extracted
PDF text (length-capped), cached 7d via speasy CacheCall. Adds pypdf dep.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Register the two tools in `_builder.py`

**Files:**
- Modify: `SciQLop/components/agents/tools/_builder.py`
- Test: `tests/test_literature_tools.py`

**Interfaces — Consumes:** `literature.search_literature`, `fulltext.fetch_paper` (Tasks 1–2); `_text_tool`, `build_sciqlop_tools` (existing).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_literature_tools.py`:

```python
"""sciqlop_search_literature / sciqlop_fetch_paper tool registration."""
import asyncio
from unittest.mock import MagicMock

import SciQLop.components.agents.tools._builder as builder


def _tool(name):
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_search_tool_registered_ungated_with_schema():
    t = _tool("sciqlop_search_literature")
    assert t.get("gated", False) is False
    props = t["input_schema"]["properties"]
    assert props["query"]["type"] == "string"
    assert props["source"]["enum"] == ["arxiv", "ads", "both"]
    assert t["input_schema"]["required"] == ["query"]


def test_fetch_tool_registered():
    t = _tool("sciqlop_fetch_paper")
    assert t.get("gated", False) is False
    assert t["input_schema"]["required"] == ["id_or_url"]


def test_search_tool_handler_delegates(monkeypatch):
    import SciQLop.components.agents.tools.literature as lit
    monkeypatch.setattr(lit, "search_literature",
                        lambda q, s, n: {"content": [{"type": "text", "text": f"q={q} s={s} n={n}"}]})
    out = asyncio.run(_tool("sciqlop_search_literature")["handler"]({"query": "recon", "source": "arxiv", "max_results": 3}))
    assert out["content"][0]["text"] == "q=recon s=arxiv n=3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_literature_tools.py -v`
Expected: FAIL — `StopIteration` (tools not registered).

- [ ] **Step 3: Add the tool builders and register them**

In `SciQLop/components/agents/tools/_builder.py`, add two builder functions (e.g. near `_api_reference_tool`):

```python
def _search_literature_tool() -> Dict[str, Any]:
    from . import literature
    return _text_tool(
        "sciqlop_search_literature",
        (
            "Search the scientific literature for papers. `source` is 'arxiv' "
            "(free), 'ads' (NASA ADS — needs a configured token), or 'both' "
            "(default). Returns title, authors, year, identifier (arXiv id / ADS "
            "bibcode), DOI, URL and a short abstract. Use sciqlop_fetch_paper to "
            "read a paper's full text. Cite what you use."
        ),
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {"type": "string", "enum": ["arxiv", "ads", "both"]},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
        lambda p: literature.search_literature(
            str(p["query"]), str(p.get("source", "both")), int(p.get("max_results", 5))),
        thread=True,
    )


def _fetch_paper_tool() -> Dict[str, Any]:
    from . import fulltext
    return _text_tool(
        "sciqlop_fetch_paper",
        (
            "Fetch the full text of an arXiv paper by id or URL (e.g. '2401.01234' "
            "or an arxiv.org link). Returns cleaned text from the HTML version, "
            "falling back to the PDF. Long papers are truncated — ask for a "
            "specific section if needed."
        ),
        {"type": "object", "properties": {"id_or_url": {"type": "string"}},
         "required": ["id_or_url"]},
        lambda p: fulltext.fetch_paper(str(p["id_or_url"])),
        thread=True,
    )
```

Then add them to the read-tools list returned by `build_sciqlop_tools` — insert into the `tools` list (e.g. after `_products_tree_tool()`):

```python
        _products_tree_tool(),
        _search_literature_tool(),
        _fetch_paper_tool(),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_literature_tools.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/tools/_builder.py tests/test_literature_tools.py
git commit -m "feat(agents): register sciqlop_search_literature + sciqlop_fetch_paper tools

Two ungated, threaded read tools delegating to literature/fulltext.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Claude built-in web tools + prompt mentions (plugins repo)

**Files (work from `/var/home/jeandet/Documents/prog/plugins_sciqlop`):**
- Modify: `sciqlop_claude/sciqlop_claude/backend.py`
- Modify: `sciqlop_opencode/sciqlop_opencode/backend.py`, `sciqlop_copilot/sciqlop_copilot/backend.py` (prompt mentions)
- Test: `sciqlop_claude/sciqlop_claude/tests/test_web_tools.py`

- [ ] **Step 1: Write the failing Claude test**

Create `sciqlop_claude/sciqlop_claude/tests/test_web_tools.py`:

```python
"""Claude backend allows the built-in WebSearch/WebFetch tools."""
import asyncio

import pytest


def test_ensure_client_allows_web_tools(monkeypatch):
    pytest.importorskip("claude_agent_sdk")
    from sciqlop_claude import backend as bk

    captured = {}

    class _FakeClient:
        def __init__(self, options):
            captured["options"] = options

        async def connect(self):
            return None

    monkeypatch.setattr(bk, "ClaudeSDKClient", _FakeClient)

    inst = bk.ClaudeBackend.__new__(bk.ClaudeBackend)
    inst._client = None
    inst._tools = []
    inst._model = None
    inst._resume = None
    inst._confirm_cb = None
    inst._ask_question_cb = None

    asyncio.run(inst._ensure_client())
    allowed = captured["options"].allowed_tools
    assert "WebSearch" in allowed
    assert "WebFetch" in allowed
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from the plugins repo root):
```
uv run --project /var/home/jeandet/Documents/prog/SciQLop pytest sciqlop_claude/sciqlop_claude/tests/test_web_tools.py -v
```
Expected: FAIL — `WebSearch` not in `allowed_tools`.

- [ ] **Step 3: Add the web tools to Claude's `allowed_tools`**

In `sciqlop_claude/sciqlop_claude/backend.py`, in `_ensure_client`, change:
```python
        allowed = [f"mcp__{_MCP_SERVER_NAME}__{t['name']}" for t in self._tools]
```
to:
```python
        allowed = [f"mcp__{_MCP_SERVER_NAME}__{t['name']}" for t in self._tools]
        allowed += ["WebSearch", "WebFetch"]  # built-in web search + page fetch (ungated)
```

- [ ] **Step 4: Run the Claude test (GREEN) + the rest of the suite**

Run:
```
uv run --project /var/home/jeandet/Documents/prog/SciQLop pytest sciqlop_claude/sciqlop_claude/tests/ -v
```
Expected: PASS (existing tests + the new one).

- [ ] **Step 5: Add a one-line tool mention to each backend prompt**

In each of the three `SYSTEM_PROMPT`s, in the **read tools** list, add a bullet for the literature tools. For `sciqlop_claude` and `sciqlop_opencode` (parenthesised-literal style), insert after the `sciqlop_products_tree` bullet:
```python
    "  • sciqlop_search_literature(query, source?, max_results?) / "
    "sciqlop_fetch_paper(id_or_url) — search arXiv + NASA ADS for papers and "
    "read an arXiv paper's full text. Use these to ground and cite claims.\n"
```
For `sciqlop_copilot` (triple-quoted RULES), add a RULES bullet:
```
- To ground or cite a claim, use sciqlop_search_literature (arXiv + ADS) and sciqlop_fetch_paper (full text).
```
For `sciqlop_claude` only, also add (after the literature bullet) a note about the built-in web:
```python
    "  • WebSearch / WebFetch — general web search and page fetch when the "
    "scholarly tools are not enough.\n"
```

- [ ] **Step 6: Verify parse + commit**

Run (from the plugins repo root):
```
uv run --isolated --no-project --with pytest python -c "import ast; [ast.parse(open(p).read()) for p in ['sciqlop_claude/sciqlop_claude/backend.py','sciqlop_opencode/sciqlop_opencode/backend.py','sciqlop_copilot/sciqlop_copilot/backend.py']]; print('ok')"
git grep -c "sciqlop_search_literature" -- '*/backend.py'
```
Expected: `ok`; the grep reports `1` for each of the three backends.

```bash
cd /var/home/jeandet/Documents/prog/plugins_sciqlop
git add sciqlop_claude/sciqlop_claude/backend.py sciqlop_opencode/sciqlop_opencode/backend.py sciqlop_copilot/sciqlop_copilot/backend.py sciqlop_claude/sciqlop_claude/tests/test_web_tools.py
git commit -m "feat(agents): Claude WebSearch/WebFetch + literature-tool prompt mentions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- `literature.py` (Paper, arXiv/ADS search via speasy http+cache, ads_token, search_literature) → Task 1.
- ADS token keyring `ConfigEntry` → Task 1 (`AdsCredentialsSettings`).
- `fulltext.py` (HTML→PDF, pypdf) → Task 2.
- Two ungated `thread=True` tools → Task 3.
- Claude `WebSearch`/`WebFetch` → Task 4; prompt mentions (all 3) → Task 4.
- `pypdf` dependency → Task 2. speasy http+cache (no httpx) → Tasks 1–2. ✓

**Placeholder scan:** none — full module code and exact commands.

**Type consistency:** `Paper` fields and `search_literature(query, source, max_results) -> {"content": [...]}` / `fetch_paper(id_or_url) -> {"content": [...]}` are used identically in Tasks 1–3; tool names `sciqlop_search_literature` / `sciqlop_fetch_paper` match across Tasks 3–4; `AdsCredentialsSettings().token` matches between Task 1's settings class and `ads_token()`.
