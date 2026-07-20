"""Hand-rolled field-weighted BM25 (BM25F) over a search domain's corpus.
Two fields per entry -- the clean path/mission/instrument hierarchy
(path_key) and the free-text metadata prose that follows it -- so an
identifier match (e.g. a mission name) can be weighted higher than a
prose match, without needing per-word heuristics: see docs/superpowers/
specs/2026-07-20-smart-search-bm25-ranking-design.md for why plain BM25
and every semantic-blending alternative were tried and rejected first."""
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence

from SciQLop.components.smart_search.domain import NodeSnapshot

_TOKEN_RE = re.compile(r'[a-z0-9]+')
_K1 = 1.5
_B = 0.75
_W_PATH = 6.0
_W_META = 1.0


def _tokenize(text: str) -> list:
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class BM25Index:
    path_keys: list
    path_inverted: dict
    meta_inverted: dict
    path_len: list
    meta_len: list
    path_avgdl: float
    meta_avgdl: float
    doc_count: int


def _invert(field_tokens: list) -> dict:
    inverted = defaultdict(dict)
    for doc_id, toks in enumerate(field_tokens):
        for term, count in Counter(toks).items():
            inverted[term][doc_id] = count
    return dict(inverted)


def build(snapshot: Sequence[NodeSnapshot]) -> BM25Index:
    path_keys = [n.path_key for n in snapshot]
    path_tokens = [_tokenize(n.path_key) for n in snapshot]
    meta_tokens = [_tokenize(n.raw_text[len(n.path_key):]) for n in snapshot]

    path_len = [len(t) for t in path_tokens]
    meta_len = [len(t) for t in meta_tokens]
    doc_count = len(path_keys)
    return BM25Index(
        path_keys=path_keys,
        path_inverted=_invert(path_tokens),
        meta_inverted=_invert(meta_tokens),
        path_len=path_len,
        meta_len=meta_len,
        path_avgdl=(sum(path_len) / doc_count) if doc_count else 1.0,
        meta_avgdl=(sum(meta_len) / doc_count) if doc_count else 1.0,
        doc_count=doc_count,
    )


def _idf(index: BM25Index, term: str) -> float:
    n = len(set(index.path_inverted.get(term, {})) | set(index.meta_inverted.get(term, {})))
    return math.log((index.doc_count - n + 0.5) / (n + 0.5) + 1)


def score(index: BM25Index, query: str) -> dict:
    """Returns {path_key: raw_bm25f_score} for every entry with at least
    one matching term. Empty dict if the query has no vocabulary overlap
    with the corpus at all."""
    scores = defaultdict(float)
    for term in _tokenize(query):
        idf = _idf(index, term)
        path_postings = index.path_inverted.get(term, {})
        meta_postings = index.meta_inverted.get(term, {})
        for doc_id in set(path_postings) | set(meta_postings):
            tf = _W_PATH * path_postings.get(doc_id, 0) + _W_META * meta_postings.get(doc_id, 0)
            doc_len = _W_PATH * index.path_len[doc_id] + _W_META * index.meta_len[doc_id]
            avgdl = _W_PATH * index.path_avgdl + _W_META * index.meta_avgdl
            denom = tf + _K1 * (1 - _B + _B * doc_len / avgdl)
            scores[doc_id] += idf * (tf * (_K1 + 1)) / denom
    return {index.path_keys[doc_id]: s for doc_id, s in scores.items()}
