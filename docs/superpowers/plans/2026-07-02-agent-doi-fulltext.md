# DOI/bibcode full-text via ADS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `sciqlop_fetch_paper` so `id_or_url` also accepts a DOI or an ADS bibcode — resolved via NASA ADS to an arXiv id when an open-access copy exists, reusing the existing arXiv fetch chain unchanged; paywalled papers with no open-access copy report that cleanly.

**Architecture:** Two source files change. `literature.py` gains `_resolve_via_ads_impl(identifier, kind)` (pure, mirrors the existing `_search_ads_impl` pattern) wrapped in a `CacheCall`. `fulltext.py` gains `_classify_identifier` (arxiv/doi/bibcode routing) and extracts the existing HTML→ar5iv→PDF logic into `_fetch_arxiv_paper(arxiv_id)` so both the direct-arXiv path and the ADS-resolved path call the exact same code. No new tool name; `_builder.py`'s existing `_fetch_paper_tool` description text is updated to mention DOI/bibcode.

**Tech Stack:** Python, `speasy.core.http`/`speasy.core.cache.CacheCall` (existing pattern), pytest + pytest-qt.

## Global Constraints

- All commands run with `uv run`; canonical run `uv run pytest --no-xvfb <path> -q`.
- Every test importing from `SciQLop.components.agents.tools.*` (including `literature.py`/`fulltext.py`) must take pytest-qt's `qtbot` fixture and import the module **inside** the test function, matching the existing pattern in `tests/test_literature.py`/`tests/test_fulltext.py` (`_lit(qtbot)`/`_ft(qtbot)` helpers). Do NOT edit `tests/conftest.py` or `tools/__init__.py`.
- Mock HTTP by monkeypatching the module-level `http.get` attribute (`lit.http.get` / `ft.http.get`), matching the existing `test_search_ads_impl_parses` / `test_fetch_paper_uses_html` pattern — NOT dependency injection via function parameters (that's the newer `fetch.py`/`describe.py` style; this feature extends older files, follow their established convention).
- **⚠️ This dev machine has a real ADS token configured** (via `AdsCredentialsSettings`, confirmed live 2026-07-02). Any test that reaches the DOI/bibcode path MUST explicitly `monkeypatch.setattr(lit_or_ft.literature, "ads_token", ...)` (or the module's own `ads_token` reference) — never leave it to fall through to the real `ads_token()`, or the test will silently attempt a live network call on machines with a configured token.
- Verified live against the real ADS API (`https://api.adsabs.harvard.edu/v1/search/query`) on 2026-07-02:
  - Query syntax: `q=doi:"10.3847/1538-4357/acaf6c"` (DOI, quoted) or `q=bibcode:2023ApJ...945...28R` (bibcode, unquoted), `fl=identifier`, `rows=1`.
  - Open-access record (`2023ApJ...945...28R`) → `identifier` list contains `"arXiv:2301.00903"`.
  - Paywalled record (`2008JGRA..113.7216D`, Wiley) → `identifier` list is `["2008JGRA..113.7216D", "10.1029/2007JA012998"]`, **no** `"arXiv:"` entry.
- `ads_token()` already exists in `literature.py` (settings-first, then `ADS_API_TOKEN` env, else `None`) — reuse it, do not duplicate.
- `_extract_arxiv_id` (in `fulltext.py`) and `_ARXIV_ID` (its regex) are unchanged — arXiv detection keeps its current behavior and priority.
- DOI regex: `^10\.\d{4,9}/\S+$` (case-insensitive). Verified it does NOT match the arXiv regex and does NOT match a bibcode shape (checked against real examples above).
- Anything not arXiv and not DOI is treated as a bibcode — passed through as-is to the `bibcode:` ADS query field.
- Tool description in `_builder.py` gets updated wording (no schema change — still one string param `id_or_url`, no new required/optional fields).

---

### Task 1: `literature.py` — `_resolve_via_ads_impl`

**Files:**
- Modify: `SciQLop/components/agents/tools/literature.py`
- Modify: `tests/test_literature.py`

**Interfaces:**
- Produces:
  - `_resolve_via_ads_impl(identifier: str, kind: str) -> Optional[str]` — `kind` is `"doi"` or `"bibcode"`. Returns the arXiv id (without the `arXiv:` prefix) found in the ADS record's `identifier` list, or `None` if there's no token, no matching record, or no `arXiv:` entry.
  - `resolve_via_ads` — the same function wrapped in `CacheCall(cache_retention=604800, is_pure=True)` (7 days, mirrors `fetch_paper`'s existing retention and immutable-paper assumption), exported at module level.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_literature.py` (the file already has `_lit(qtbot)`, `_ADS_JSON`, and other fixtures — add these below the existing tests):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_literature.py -k resolve_via_ads -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_resolve_via_ads_impl'`.

- [ ] **Step 3: Write minimal implementation**

Add to `SciQLop/components/agents/tools/literature.py`, right after `search_ads = CacheCall(...)(_search_ads_impl)`:

```python
_ADS_LOOKUP_RETENTION = 604800  # 7 d — same immutable-paper assumption as fetch_paper


def _resolve_via_ads_impl(identifier: str, kind: str) -> Optional[str]:
    """Resolve a DOI or ADS bibcode to an arXiv id when an open-access copy
    exists. Returns None if there's no token, no record, or no open-access
    (arXiv) copy — NASA ADS only indexes abstracts for paywalled journals."""
    token = ads_token()
    if not token:
        return None
    q = f'doi:"{identifier}"' if kind == "doi" else f"bibcode:{identifier}"
    r = http.get("https://api.adsabs.harvard.edu/v1/search/query",
                 headers={"Authorization": f"Bearer {token}"},
                 params={"q": q, "rows": "1", "fl": "identifier"}, timeout=30)
    if not r.ok:
        return None
    docs = (r.json().get("response") or {}).get("docs") or []
    if not docs:
        return None
    for ident in docs[0].get("identifier") or []:
        if ident.startswith("arXiv:"):
            return ident[len("arXiv:"):]
    return None


resolve_via_ads = CacheCall(cache_retention=_ADS_LOOKUP_RETENTION, is_pure=True)(_resolve_via_ads_impl)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_literature.py -q`
Expected: PASS (all tests in the file, including the 5 new ones).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/literature.py tests/test_literature.py
git commit -m "feat(agents): literature.resolve_via_ads — DOI/bibcode to arXiv id via ADS"
```

---

### Task 2: `fulltext.py` — identifier classification + routing, reuse the existing arXiv chain

**Files:**
- Modify: `SciQLop/components/agents/tools/fulltext.py`
- Modify: `SciQLop/components/agents/tools/_builder.py` (description text only)
- Modify: `tests/test_fulltext.py`

**Interfaces:**
- Consumes: `literature.ads_token`, `literature.resolve_via_ads` (Task 1).
- Produces:
  - `_classify_identifier(id_or_url: str) -> str` — returns `"arxiv"`, `"doi"`, or `"bibcode"`.
  - `_fetch_arxiv_paper(arxiv_id: str) -> dict` — the existing HTML→ar5iv→PDF logic, extracted unchanged from the current `_fetch_paper_impl` body.
  - `_fetch_paper_impl(id_or_url: str) -> dict` — now routes through `_classify_identifier`; arXiv path calls `_fetch_arxiv_paper` directly; DOI/bibcode path checks `literature.ads_token()` first, then calls `literature.resolve_via_ads(identifier, kind)`, then `_fetch_arxiv_paper` on a hit.

- [ ] **Step 1: Write the failing tests**

In `tests/test_fulltext.py`, first **replace** the existing `test_fetch_paper_unresolvable` test (its behavior changes — a non-arXiv, non-DOI string is now treated as a bibcode attempt, not an immediate failure) with these, and add the classification test:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_fulltext.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_classify_identifier'` (and `ft.literature` not yet imported).

- [ ] **Step 3: Write minimal implementation**

In `SciQLop/components/agents/tools/fulltext.py`, add the import and DOI regex near the top (after the existing `_ARXIV_ID` line):

```python
from . import literature

_DOI_ID = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
```

Replace the current `_fetch_paper_impl` function body — extract its arXiv-fetch logic into `_fetch_arxiv_paper`, add `_classify_identifier`, and rewrite `_fetch_paper_impl` as the router:

```python
def _fetch_arxiv_paper(arxiv_id: str) -> dict:
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


def _classify_identifier(id_or_url: str) -> str:
    s = (id_or_url or "").strip()
    if _extract_arxiv_id(s):
        return "arxiv"
    if _DOI_ID.match(s):
        return "doi"
    return "bibcode"


def _fetch_paper_impl(id_or_url: str) -> dict:
    identifier = (id_or_url or "").strip()
    kind = _classify_identifier(identifier)
    if kind == "arxiv":
        return _fetch_arxiv_paper(_extract_arxiv_id(identifier))
    if not literature.ads_token():
        return _msg("ADS token required to resolve DOI/bibcode identifiers — "
                    "set one in settings or ADS_API_TOKEN")
    resolved_arxiv_id = literature.resolve_via_ads(identifier, kind)
    if not resolved_arxiv_id:
        return _msg(f"no open-access full text found via ADS for {identifier!r}; "
                    "only the abstract is available — provide the PDF directly if you have access")
    return _fetch_arxiv_paper(resolved_arxiv_id)
```

Now update `SciQLop/components/agents/tools/_builder.py`'s `_fetch_paper_tool` description (schema and handler line are unchanged — only the description string):

```python
def _fetch_paper_tool() -> Dict[str, Any]:
    from . import fulltext
    return _text_tool(
        "sciqlop_fetch_paper",
        (
            "Fetch the full text of a paper by arXiv id/URL, DOI, or ADS bibcode "
            "(e.g. '2401.01234', an arxiv.org link, '10.3847/1538-4357/acaf6c', or "
            "'2023ApJ...945...28R') — auto-detected. DOI/bibcode resolution goes "
            "via NASA ADS and only succeeds when an open-access (usually arXiv) "
            "copy exists; paywalled papers with no open-access copy report that "
            "cleanly. Returns cleaned text from the HTML version, falling back to "
            "the PDF. Long papers are truncated — ask for a specific section if "
            "needed."
        ),
        {"type": "object", "properties": {"id_or_url": {"type": "string"}},
         "required": ["id_or_url"]},
        lambda p: fulltext.fetch_paper(str(p["id_or_url"])),
        thread=True,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_fulltext.py -q`
Expected: PASS (all tests, including the existing `test_extract_arxiv_id_from_url_and_bare`, `test_html_to_text_strips_markup_and_scripts`, `test_fetch_paper_uses_html`, `test_fetch_paper_pdf_fallback` — unaffected by the refactor — plus the 5 new/replaced tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/fulltext.py SciQLop/components/agents/tools/_builder.py tests/test_fulltext.py
git commit -m "feat(agents): fetch_paper — DOI/bibcode via ADS, reuses arXiv fetch chain"
```

---

### Task 3: suite sanity + registration check

**Files:** Test only (no source change unless a regression surfaces).

- [ ] **Step 1: Run the literature/fulltext tests together**

Run: `uv run pytest --no-xvfb tests/test_literature.py tests/test_fulltext.py tests/test_literature_tools.py -q`
Expected: PASS (all tests across the three files — Task 1's 5 new + Task 2's 5 new/replaced + all pre-existing tests in these files, including the untouched `test_literature_tools.py` registration tests).

- [ ] **Step 2: Confirm the tool schema/gating is unchanged**

Run:
```bash
QT_QPA_PLATFORM=offscreen uv run python - <<'PY'
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import SciQLop.components.agents.tools._builder as b
t = next(x for x in b.build_sciqlop_tools(MagicMock()) if x["name"] == "sciqlop_fetch_paper")
assert t.get("gated", False) is False
assert t["input_schema"]["required"] == ["id_or_url"]
assert "DOI" in t["description"] and "bibcode" in t["description"]
print("OK: sciqlop_fetch_paper still ungated, schema unchanged, description mentions DOI/bibcode")
PY
```
Expected: `OK: sciqlop_fetch_paper still ungated, schema unchanged, description mentions DOI/bibcode`

- [ ] **Step 3: Commit (only if fixups were needed)**

```bash
git add -A && git commit -m "test(agents): DOI/bibcode fetch_paper suite sanity"
```

## Self-Review

**Spec coverage:**
- Detection order (arXiv → DOI → else bibcode) → Task 2 `_classify_identifier` + test. ✅
- `_resolve_via_ads` mirrors `_search_ads_impl` pattern, `CacheCall(604800)` → Task 1. ✅
- Zero duplication: arXiv-found path reuses `_fetch_arxiv_paper` verbatim, same function for both the direct-arXiv and ADS-resolved cases → Task 2. ✅
- No-token clean message, distinct from "no open-access copy" message → Task 2 (`_fetch_paper_impl` checks `ads_token()` before calling `resolve_via_ads`, since both would otherwise collapse to `None`). ✅
- Never scrapes a publisher / never bypasses a paywall → Task 2 test `test_fetch_paper_bibcode_no_open_access_reports_cleanly` explicitly asserts `http.get` is NOT called via an assertion-raising monkeypatch. ✅
- Tool surface unchanged (extends `sciqlop_fetch_paper`, no new tool, no schema change) → Task 2 `_builder.py` edit + Task 3 registration check. ✅
- Query syntax verified live (`doi:"..."` quoted, `bibcode:...` unquoted) → Task 1 `test_resolve_via_ads_builds_correct_query_for_doi_and_bibcode`, using the exact real strings captured during design. ✅

**Placeholder scan:** No TBD/TODO; every code step is complete, no "add error handling" hand-waving. ✅

**Type consistency:** `_resolve_via_ads_impl(identifier: str, kind: str) -> Optional[str]` used identically in Task 1 and Task 2's `_fetch_paper_impl` call (`literature.resolve_via_ads(identifier, kind)`); `_fetch_arxiv_paper(arxiv_id: str) -> dict` signature consistent between its extraction and both call sites. ✅

**Flagged proactively (not a gap, a note):** Task 2 explicitly REPLACES the pre-existing `test_fetch_paper_unresolvable` test rather than adding alongside it, because the old assertion ("could not resolve" for any non-arXiv string) is no longer true under the new classification — a plain string now attempts the bibcode path. This is called out in Task 2 Step 1 so the implementer doesn't leave a contradictory test in place.
