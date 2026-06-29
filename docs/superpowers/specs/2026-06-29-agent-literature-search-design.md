# Literature search & full-text access for the SciQLop agents

**Date:** 2026-06-29
**Status:** Approved (design)
**Repos:** SciQLop (tool, fetch, settings, dependency — the bulk) + plugins_sciqlop (Claude built-in web only).

## Problem

The agents' system prompts now tell them to "ground physical claims in the
literature," but they have no way to actually find or read papers — `allowed_tools`
is restricted to the sciqlop MCP tools. This adds real literature access:
scholarly search (arXiv + NASA ADS) and full-text retrieval, available to all
three agents, plus Claude's built-in web tools.

## Design

Two components, two repos.

### Component 1 — literature access (SciQLop in-tree, all three agents)

All HTTP goes through **`speasy.core.http.get`** (retries, proxy, certifi TLS,
user-agent — consistent with how SciQLop fetches data; returns a `Response` with
`.status_code/.ok/.text/.bytes/.json`). Result caching uses
**`speasy.core.cache.CacheCall`** (disk cache). No `httpx`.

#### `SciQLop/components/agents/tools/literature.py` (new — search)
- `Paper` dataclass: `title, authors (list), year, venue, identifier (arXiv id or
  ADS bibcode), doi, url, abstract`.
- `search_arxiv(query: str, max_results: int) -> list[Paper]` — GET
  `http://export.arxiv.org/api/query` (`search_query`, `max_results`); parse the
  Atom feed with stdlib `xml.etree.ElementTree`. Wrapped with
  `@CacheCall(cache_retention=21600, is_pure=False)` (~6 h).
- `search_ads(query: str, max_results: int, token: str) -> list[Paper]` — GET
  `https://api.adsabs.harvard.edu/v1/search/query` with
  `headers={"Authorization": f"Bearer {token}"}`, `params={"q":…, "rows":…,
  "fl":"title,author,year,bibcode,doi,abstract"}`; parse JSON. Same caching.
- `ads_token() -> str | None` — keyring first (see token storage), else
  `ADS_API_TOKEN` env; `None`/empty disables ADS.
- `search_literature(query: str, source: str = "both", max_results: int = 5) -> dict`
  — runs the selected sources; if `source` includes ads but no token, skips ADS
  and appends a one-line "(ADS skipped: no token)" note; renders compact markdown
  per paper (title, authors et al., year, venue, identifier, doi, url, abstract
  truncated ~300 chars); returns the `{"content": [...]}` tool shape. Clean
  message on network error / no results (never raises).

#### `SciQLop/components/agents/tools/fulltext.py` (new — full text)
- `fetch_paper(id_or_url: str) -> dict` — resolve an arXiv id or URL, then:
  1. GET arXiv HTML (`https://arxiv.org/html/<id>`); on miss/non-HTML, GET
     `https://ar5iv.org/abs/<id>`; strip markup to text (stdlib `html.parser`).
  2. If no HTML, GET the PDF (`https://arxiv.org/pdf/<id>`) `.bytes` and extract
     text with **`pypdf`**.
  Returns cleaned text in the `{"content": [...]}` shape, length-capped (~40k
  chars) with a "(truncated — fetch a specific section)" note for long papers.
  Wrapped with `@CacheCall(cache_retention=604800, is_pure=False)` (~7 d; a
  published paper is immutable). Clean message on failure.

#### ADS token storage
Use SciQLop's built-in keyring support for `ConfigEntry` (the same mechanism the
CoCat plugin uses): a class declares `_keyring_ = KeyringMapping(service_field,
username_field, password_field)` and on `save()` the password field is written to
the OS keyring and popped from the YAML dump; on load it is repopulated from
keyring (`SciQLop/components/settings/backend/entry.py`).

- New `ConfigEntry` (e.g. `AdsCredentialsSettings`, category APPLICATION,
  subcategory "Agent chat"):
  - `_keyring_ = KeyringMapping("service", "username", "token")`.
  - `service: str = "nasa-ads"` and `username: str = "ads_api_token"` —
    constants needed only to key the credential (`_save_keyring` requires all
    three non-empty); both `json_schema_extra={"widget": "hidden"}`.
  - `token: str = Field(default="", description="NASA ADS API token",
    json_schema_extra={"widget": "password"})` — renders as a masked field in the
    settings page, stored in keyring, never written to YAML.
- `ads_token() -> str | None` (in `literature.py`): returns
  `AdsCredentialsSettings().token` (keyring-populated) if non-empty, else
  `os.environ.get("ADS_API_TOKEN") or None`.
- `ads_token()` returns the keyring value, else `ADS_API_TOKEN` env.

#### Tools (`_builder.py`)
- `sciqlop_search_literature` and `sciqlop_fetch_paper`, both **ungated read
  tools** built with `_text_tool(..., thread=True)` (blocking HTTP runs in the IO
  pool), added to the read-tools list in `build_sciqlop_tools`.
  - `sciqlop_search_literature` schema: `{query (required), source: enum
    [arxiv, ads, both] = both, max_results: int = 5}`.
  - `sciqlop_fetch_paper` schema: `{id_or_url (required)}`.

### Component 2 — Claude built-in web (plugins_sciqlop)
- `sciqlop_claude/sciqlop_claude/backend.py`: `allowed_tools += ["WebSearch",
  "WebFetch"]`. Ungated (not in `_gated_names`, so `_permission_check` allows).

### Prompts (all three backends)
- Add a one-line mention of `sciqlop_search_literature` and `sciqlop_fetch_paper`
  to each read-tools list (the tools' own `description` carries full usage); add a
  line about `WebSearch`/`WebFetch` to the Claude prompt.

## Dependency

Add `pypdf` to SciQLop's `pyproject.toml` (PDF-fallback text extraction; pure
Python, no native build). `httpx` is **not** added — speasy provides HTTP.

## Data flow

agent → `sciqlop_search_literature` → `search_arxiv`/`search_ads`
(`speasy.core.http.get`, `CacheCall`) → ranked markdown of `Paper`s with ids/URLs
→ agent picks one → `sciqlop_fetch_paper(id_or_url)` → HTML (arxiv/ar5iv) or PDF
(`pypdf`) → cleaned full text. Claude may also use `WebSearch`/`WebFetch` directly.

## Error handling

- Network error / timeout / non-200 → the tool returns a clear text message, not
  an exception (the `_text_tool` wrapper also converts exceptions to error
  content).
- ADS requested without a token → ADS skipped with a note; arXiv still runs.
- `fetch_paper` with no HTML and no extractable PDF text → "could not retrieve
  full text; abstract/DOI only" message.
- Payloads bounded: abstracts ~300 chars in search; full text ~40k chars.

## Testing (SciQLop test env, `uv run pytest --no-xvfb`)

Monkeypatch `speasy.core.http.get` (no live network) and, where needed, bypass
`CacheCall` (call the undecorated inner function or use a unique query per test):
- `search_arxiv`: a sample Atom XML payload → expected `Paper`s (fields parsed).
- `search_ads`: a sample JSON payload → expected `Paper`s; and `search_ads` is not
  attempted when `ads_token()` is `None`.
- `ads_token()`: keyring value used first; falls back to `ADS_API_TOKEN` env
  (both monkeypatched).
- `search_literature`: `source="arxiv"` skips ADS; `source="both"` with no token
  emits the skip note; markdown contains title/identifier/url.
- `fetch_paper`: HTML path strips markup to text; PDF fallback path extracts text
  (monkeypatch the HTML GET to fail and `pypdf` / the PDF GET to a tiny sample).
- Tool registration: both tools present in `build_sciqlop_tools(...)`, ungated,
  with the schemas above; handlers delegate to the module functions.
- Claude backend: `allowed_tools` includes `"WebSearch"` and `"WebFetch"`.

## Out of scope

- Result caching beyond `CacheCall` (e.g. custom invalidation UI).
- Citation graphs / "cited by".
- Other databases (INSPIRE-HEP, Semantic Scholar, CrossRef).
- Full text of paywalled, non-arXiv published papers (only abstract + DOI).
