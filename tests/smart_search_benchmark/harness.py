"""Loads the real product corpus cache and evaluates BenchmarkCase
instances against it via the exact score_query() the app uses at runtime.
See docs/superpowers/specs/2026-07-22-smart-search-benchmark-corpus-design.md."""
from dataclasses import dataclass

import numpy as np

from SciQLop.components.smart_search import bm25_index
from SciQLop.components.smart_search.registry import score_query

from tests.smart_search_benchmark.cases import DEFAULT_TOP_N, BenchmarkCase


@dataclass(frozen=True)
class RealCorpus:
    path_keys: list
    matrix: np.ndarray
    bm25: bm25_index.BM25Index
    query_model: object


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
