import pickle
from unittest.mock import MagicMock, patch

import numpy as np

from SciQLop.components.smart_search import bm25_index, model_fetch
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


def _write_fake_cache(path, model_name="fake-model"):
    # raw_text must start with its own path_key (the real convention -- see
    # SciQLop/components/products/smart_search_domain.py's `f"{k} {v}"` --
    # bm25_index.build() slices raw_text[len(path_key):] for the meta field).
    entries = {
        "root a": ("root a raw text a", np.array([1.0, 0.0])),
        "root b": ("root b raw text b", np.array([0.0, 1.0])),
    }
    with open(path, "wb") as f:
        pickle.dump({"model_name": model_name, "entries": entries}, f)


def test_load_real_corpus_parses_cache_into_real_corpus(tmp_path):
    cache_path = tmp_path / "products.pkl"
    _write_fake_cache(cache_path)
    fake_model = MagicMock()

    with patch.object(model_fetch, "load_model", return_value=fake_model) as mock_load:
        corpus = harness.load_real_corpus(cache_path)

    assert corpus.path_keys == ["root a", "root b"]
    assert corpus.matrix.shape == (2, 2)
    assert corpus.query_model is fake_model
    mock_load.assert_called_once_with("fake-model", cache_dir=harness._cache_dir())


def test_load_real_corpus_builds_bm25_index_from_cached_raw_text(tmp_path):
    cache_path = tmp_path / "products.pkl"
    _write_fake_cache(cache_path)

    with patch.object(model_fetch, "load_model", return_value=MagicMock()):
        corpus = harness.load_real_corpus(cache_path)

    scores = bm25_index.score(corpus.bm25, "raw")
    assert set(scores.keys()) == {"root a", "root b"}
