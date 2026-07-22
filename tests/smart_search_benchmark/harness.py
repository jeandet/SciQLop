"""Loads the real product corpus cache and evaluates BenchmarkCase
instances against it via the exact score_query() the app uses at runtime.
See docs/superpowers/specs/2026-07-22-smart-search-benchmark-corpus-design.md."""
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from SciQLop.components.smart_search import _cache_dir, _index_cache_dir, bm25_index, model_fetch
from SciQLop.components.smart_search.domain import NodeSnapshot
from SciQLop.components.smart_search.registry import score_query

from tests.smart_search_benchmark.cases import DEFAULT_TOP_N, BenchmarkCase


@dataclass(frozen=True)
class RealCorpus:
    path_keys: list
    matrix: np.ndarray
    bm25: bm25_index.BM25Index
    query_model: object


CACHE_PATH = Path(_index_cache_dir()) / "products.pkl"


def load_real_corpus(cache_path: Path = CACHE_PATH) -> RealCorpus:
    # Same pickle cache index_worker.py writes/reads under SciQLop's own
    # platformdirs cache dir -- never sourced from anywhere untrusted, so
    # pickle's arbitrary-code-execution risk on load doesn't apply here.
    with open(cache_path, "rb") as f:
        cache = pickle.load(f)
    entries = cache["entries"]
    path_keys = list(entries.keys())
    matrix = np.stack([vector for _, vector in entries.values()])
    bm25 = bm25_index.build([NodeSnapshot(k, raw_text) for k, (raw_text, _) in entries.items()])
    query_model = model_fetch.load_model(cache["model_name"], cache_dir=_cache_dir())
    return RealCorpus(path_keys=path_keys, matrix=matrix, bm25=bm25, query_model=query_model)


@dataclass(frozen=True)
class EvaluationResult:
    case: BenchmarkCase
    passed: bool
    best_rank: int | None
    total_candidates: int


def evaluate(case: BenchmarkCase, corpus: RealCorpus) -> EvaluationResult:
    scores = score_query(case.query, corpus.path_keys, corpus.matrix, corpus.bm25, corpus.query_model)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_n = case.top_n if case.top_n is not None else DEFAULT_TOP_N

    def _matches(path_key: str) -> bool:
        return any(path_key.startswith(prefix) for prefix in case.expected_prefixes)

    best_rank = next((i + 1 for i, (path_key, _) in enumerate(ranked) if _matches(path_key)), None)
    passed = best_rank is not None and best_rank <= top_n
    return EvaluationResult(case=case, passed=passed, best_rank=best_rank, total_candidates=len(ranked))
