from unittest.mock import patch

import numpy as np

from tests.smart_search_benchmark import harness
from tests.smart_search_benchmark.cases import BenchmarkCase
from tests.smart_search_benchmark.harness import RealCorpus


def _corpus() -> RealCorpus:
    # score_query is mocked in every test below, so the corpus's own field
    # values never get touched -- only its presence/type matters.
    return RealCorpus(path_keys=[], matrix=np.zeros((0, 2)), bm25=None, query_model=None)


def test_evaluate_passes_when_expected_prefix_within_top_n():
    case = BenchmarkCase(query="q", expected_prefixes=["root MMS1 FGM"], top_n=10)
    scores = {"root MMS1 FGM leaf": 90.0, "root decoy": 10.0}

    with patch.object(harness, "score_query", return_value=scores):
        result = harness.evaluate(case, _corpus())

    assert result.passed
    assert result.best_rank == 1
    assert result.total_candidates == 2


def test_evaluate_fails_when_expected_prefix_outside_top_n():
    case = BenchmarkCase(query="q", expected_prefixes=["root MMS1 FGM"], top_n=2)
    scores = {"root MMS1 FGM leaf": 10.0, "root decoy a": 90.0, "root decoy b": 80.0}

    with patch.object(harness, "score_query", return_value=scores):
        result = harness.evaluate(case, _corpus())

    assert not result.passed
    assert result.best_rank == 3


def test_evaluate_reports_none_rank_when_prefix_never_matches():
    case = BenchmarkCase(query="q", expected_prefixes=["root MMS1 FGM"], top_n=10)
    scores = {"root unrelated": 50.0}

    with patch.object(harness, "score_query", return_value=scores):
        result = harness.evaluate(case, _corpus())

    assert not result.passed
    assert result.best_rank is None


def test_evaluate_uses_default_top_n_when_case_omits_it():
    case = BenchmarkCase(query="q", expected_prefixes=["root MMS1 FGM"])  # top_n=None
    scores = {f"root decoy {i}": float(100 - i) for i in range(harness.DEFAULT_TOP_N)}
    scores["root MMS1 FGM leaf"] = 0.0  # ranks last: DEFAULT_TOP_N + 1

    with patch.object(harness, "score_query", return_value=scores):
        result = harness.evaluate(case, _corpus())

    assert not result.passed
    assert result.best_rank == harness.DEFAULT_TOP_N + 1


def test_evaluate_any_of_multiple_expected_prefixes_counts():
    case = BenchmarkCase(query="q", expected_prefixes=["root SCM", "root FGM"], top_n=10)
    scores = {"root decoy": 90.0, "root FGM leaf": 50.0}

    with patch.object(harness, "score_query", return_value=scores):
        result = harness.evaluate(case, _corpus())

    assert result.passed
    assert result.best_rank == 2
