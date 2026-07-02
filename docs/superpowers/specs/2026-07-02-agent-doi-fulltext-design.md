# DOI/bibcode full-text access via ADS

**Date:** 2026-07-02
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — extends `SciQLop/components/agents/tools/{literature,fulltext}.py`).

## Problem

From the in-app Claude feedback: `sciqlop_search_literature` + `sciqlop_fetch_paper`
work well, but `fetch_paper` is arXiv-only. The agent hit the Wiley paywall on
Borovsky (2008) and Xu & Borovsky (2015) — papers ADS could find but had no
arXiv-only path to reach — and had to be handed a PDF manually and web-scrape
for a unit ("T_p in eV"). A "fetch full text by DOI/bibcode (via ADS)" tool
closes that gap for the subset of papers that DO have an open-access copy.

This is Tier-2 item #2 of the agent-MCP-tooling backlog (item #1,
`sciqlop_describe_product`, shipped 2026-07-02).

## Key finding (grounds the design, verified live against the real ADS API)

NASA ADS does **not** host full text for paywalled journals — only abstracts —
but it tracks, per record, whether an open-access copy exists (typically an
arXiv eprint). Verified with the configured ADS token against real records:

- **Paywalled** (`2008JGRA..113.7216D`, Wiley/JGR): `esources: ["PUB_HTML"]`,
  `identifier` contains only the bibcode and DOI — **no `arXiv:` entry**.
- **Open-access** (`2023ApJ...945...28R`): `esources: ["EPRINT_HTML",
  "EPRINT_PDF", "PUB_HTML", "PUB_PDF"]`, and critically `identifier` contains a
  plain `"arXiv:2301.00903"` entry.
- Both `doi:"10.3847/1538-4357/acaf6c"` and `bibcode:2023ApJ...945...28R` query
  syntax against `https://api.adsabs.harvard.edu/v1/search/query` return the
  same record.

So the resolution mechanism is: **query ADS by DOI or bibcode, scan the
`identifier` list for an `arXiv:` entry, and if found, hand that arXiv id to
the existing, unmodified arXiv fetch chain.** No new HTML/PDF extraction code;
no publisher scraping; no paywall bypass — for a paywalled paper with no
open-access copy, the tool reports that cleanly and stops.

## Design

Extends the existing `sciqlop_fetch_paper` tool (`tools/fulltext.py`) — **no
new tool name**, consistent with the agent already knowing this tool by name.

### Identifier detection (in `id_or_url`)

Checked in this order, each check independent of the others:

1. **arXiv id/URL** — existing `_ARXIV_ID` regex (unchanged; today's arXiv
   callers are unaffected, this check runs first).
2. **DOI** — `^10\.\d{4,9}/\S+$` (case-insensitive; matches the observed real
   DOIs, e.g. `10.3847/1538-4357/acaf6c`, `10.1029/2007JA012998`).
3. **Else: ADS bibcode** — anything not matching the above is passed through
   as-is to the `bibcode:` ADS query field.

### `_resolve_via_ads(identifier: str, kind: Literal["doi","bibcode"]) -> Optional[str]`

New function in `tools/literature.py` (reuses `ads_token()`, `http.get`, the
existing ADS query pattern):

- Query `https://api.adsabs.harvard.edu/v1/search/query` with
  `q=doi:"<identifier>"` (kind `"doi"`) or `q=bibcode:<identifier>` (kind
  `"bibcode"`), `fl=identifier`, `rows=1`.
- On a hit, scan the returned `identifier` list for an entry with the literal
  prefix `arXiv:` and return the id after the colon (e.g. `"2301.00903"`).
- No hit, or no `arXiv:` entry in `identifier` → return `None`.
- Wrapped in `CacheCall(cache_retention=604800, is_pure=True)` (7 days — same
  immutable-paper assumption as `fetch_paper`'s existing cache; a distinct
  cache from the arXiv-fetch cache since it's a separate HTTP call).

### `fetch_paper` orchestration (in `tools/fulltext.py`)

`_fetch_paper_impl(id_or_url)` gains a routing prefix:

1. If `id_or_url` matches an arXiv id/URL → **unchanged existing behavior**
   (extract arXiv id, run the HTML→ar5iv→PDF chain).
2. Else if it matches a DOI or looks like a bibcode:
   - No ADS token configured (`ads_token()` is `None`) → return
     `"ADS token required to resolve DOI/bibcode identifiers — set one in "
     "settings or ADS_API_TOKEN"` (mirrors `search_literature`'s existing
     "(ADS skipped: no token)" note).
   - Otherwise call `_resolve_via_ads`. If it returns an arXiv id, pass that id
     into the **same existing arXiv-fetch code path** used in step 1 — zero
     duplication of the HTML/PDF extraction logic.
   - If it returns `None` → return
     `"no open-access full text found via ADS for '<id_or_url>'; only the "
     "abstract is available — provide the PDF directly if you have access"`.
     Never attempt publisher scraping or any paywall bypass.

### Testing (offline where possible)

- **Pure classification:** a `_classify_identifier(id_or_url) -> Literal["arxiv",
  "doi", "bibcode"]` helper (or equivalent inline logic), tested against real
  observed strings: `"2301.00903"` (arXiv), `"10.3847/1538-4357/acaf6c"` (DOI),
  `"2023ApJ...945...28R"` (bibcode) — plus an arXiv URL form.
- **`_resolve_via_ads`:** inject a fake ADS JSON payload (matching the real
  shapes captured above) → assert arXiv-id extraction from `identifier` when
  present, and `None` when the payload has no `arXiv:` entry (paywalled case).
- **Tool-level (`_fetch_paper_impl`):** no-token path returns the clear message
  without any HTTP call; DOI/bibcode-with-arXiv path delegates to the existing
  HTML/PDF chain (assert via monkeypatch/call tracking that no new extraction
  logic runs — same function, same code path as the arXiv-only case);
  DOI/bibcode-without-arXiv path returns the "no open-access" message and makes
  no publisher HTTP call.

## Out of scope (tracked in backlog)

Ephemeris/coordinate transforms (3DView); generic CDF/netCDF/HDF5 file
inspector; background-job runner. Publisher-site scraping or any paywall
circumvention is explicitly rejected, not deferred.
