"""arXiv + NASA ADS literature search for the SciQLop agents."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from defusedxml import ElementTree as ET  # XXE / billion-laughs-safe XML parsing

from speasy.core import http
from speasy.core.cache import CacheCall

from SciQLop.components.agents.settings import AdsCredentialsSettings

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


def ads_token() -> Optional[str]:
    try:
        tok = AdsCredentialsSettings().token
        if tok:
            return tok
    except Exception:
        pass
    return os.environ.get("ADS_API_TOKEN") or None


def _search_arxiv_impl(query: str, max_results: int) -> List[Paper]:
    sq = query if ":" in query else f"all:{query}"
    r = http.get("https://export.arxiv.org/api/query",
                 params={"search_query": sq, "max_results": str(max_results)}, timeout=30)
    return _parse_arxiv_atom(r.text) if r.ok else []


search_arxiv = CacheCall(cache_retention=_SEARCH_RETENTION, is_pure=True)(_search_arxiv_impl)


def _search_ads_impl(query: str, max_results: int) -> List[Paper]:
    token = ads_token()
    if not token:
        return []
    r = http.get("https://api.adsabs.harvard.edu/v1/search/query",
                 headers={"Authorization": f"Bearer {token}"},
                 params={"q": query, "rows": str(max_results),
                         "fl": "title,author,year,bibcode,doi,abstract"}, timeout=30)
    return _parse_ads_json(r.json()) if r.ok else []


search_ads = CacheCall(cache_retention=_SEARCH_RETENTION, is_pure=True)(_search_ads_impl)


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
                papers += search_ads(query, max_results)
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
