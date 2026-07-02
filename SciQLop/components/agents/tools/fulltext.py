"""Fetch a paper's full text: arXiv id/URL directly (HTML, falling back to
PDF), or a DOI/bibcode resolved to an open-access arXiv copy via ADS."""
from __future__ import annotations

import io
import re
from html.parser import HTMLParser

from speasy.core import http
from speasy.core.cache import CacheCall

from . import literature

_FETCH_RETENTION = 604800  # 7 d — a published paper is immutable
_MAX_CHARS = 40000
_ARXIV_ID = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?", re.I)
_DOI_ID = re.compile(r"^10\.\d{4,9}/\S+$", re.I)


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
    arxiv_id = _extract_arxiv_id(identifier)
    if arxiv_id:
        return _fetch_arxiv_paper(arxiv_id)
    kind = _classify_identifier(identifier)  # arxiv already handled above → "doi" or "bibcode"
    if not literature.ads_token():
        return _msg("ADS token required to resolve DOI/bibcode identifiers — "
                    "set one in settings or ADS_API_TOKEN")
    resolved_arxiv_id = literature.resolve_via_ads(identifier, kind)
    if not resolved_arxiv_id:
        return _msg(f"no open-access full text found via ADS for {identifier!r}; "
                    "only the abstract is available — provide the PDF directly if you have access")
    return _fetch_arxiv_paper(resolved_arxiv_id)


fetch_paper = CacheCall(cache_retention=_FETCH_RETENTION, is_pure=True)(_fetch_paper_impl)
