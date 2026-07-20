from unittest.mock import patch, MagicMock
import pickle
import numpy as np

from SciQLop.components.smart_search import bm25_index, index_worker
from SciQLop.components.smart_search.domain import NodeSnapshot


def test_run_embeds_every_node_when_cache_empty(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts, **kwargs: np.array([[float(len(t)), 0.0] for t in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model) as mock_load:
        result = index_worker.run(
            [NodeSnapshot("a", "hi"), NodeSnapshot("b", "hello")],
            "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    mock_load.assert_called_once_with("minishlab/potion-base-8M", "/tmp/cache")
    assert isinstance(result, index_worker.IndexResult)
    assert set(result.embeddings.keys()) == {"a", "b"}
    assert np.array_equal(result.embeddings["a"], np.array([2.0, 0.0]))
    assert np.array_equal(result.embeddings["b"], np.array([5.0, 0.0]))


def test_run_with_empty_snapshot_returns_empty_dict_and_writes_empty_cache(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    with patch.object(index_worker.model_fetch, "load_model") as mock_load:
        result = index_worker.run([], "minishlab/potion-base-8M", "/tmp/cache", cache_path)
    mock_load.assert_not_called()
    assert result.embeddings == {}
    with open(cache_path, "rb") as f:
        cache = pickle.load(f)
    assert cache == {"model_name": "minishlab/potion-base-8M", "entries": {}}


def test_run_reuses_cached_vector_when_text_unchanged(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    cached_vec = np.array([9.0, 9.0])
    with open(cache_path, "wb") as f:
        pickle.dump({"model_name": "minishlab/potion-base-8M",
                     "entries": {"a": ("hi", cached_vec)}}, f)

    with patch.object(index_worker.model_fetch, "load_model") as mock_load:
        result = index_worker.run(
            [NodeSnapshot("a", "hi")], "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    mock_load.assert_not_called()
    assert np.array_equal(result.embeddings["a"], cached_vec)


def test_run_only_embeds_changed_entries_and_carries_unchanged_ones_through(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    cached_vec = np.array([9.0, 9.0])
    with open(cache_path, "wb") as f:
        pickle.dump({"model_name": "minishlab/potion-base-8M",
                     "entries": {"a": ("hi", cached_vec), "b": ("old text", np.array([1.0, 1.0]))}}, f)

    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts, **kwargs: np.array([[5.0, 5.0] for _ in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        result = index_worker.run(
            [NodeSnapshot("a", "hi"), NodeSnapshot("b", "new text")],
            "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    fake_model.encode.assert_called_once_with(["new text"], use_multiprocessing=False)
    assert np.array_equal(result.embeddings["a"], cached_vec)
    assert np.array_equal(result.embeddings["b"], np.array([5.0, 5.0]))


def test_run_drops_entries_no_longer_in_current_snapshot(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    with open(cache_path, "wb") as f:
        pickle.dump({"model_name": "minishlab/potion-base-8M",
                     "entries": {"a": ("hi", np.array([1.0, 1.0])), "b": ("bye", np.array([2.0, 2.0]))}}, f)

    with patch.object(index_worker.model_fetch, "load_model") as mock_load:
        result = index_worker.run(
            [NodeSnapshot("a", "hi")], "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    mock_load.assert_not_called()
    assert set(result.embeddings.keys()) == {"a"}
    # Verify removed entry "b" is also dropped from the persisted cache file
    with open(cache_path, "rb") as f:
        cache = pickle.load(f)
    assert set(cache["entries"].keys()) == {"a"}


def test_run_discards_whole_cache_on_model_mismatch(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    with open(cache_path, "wb") as f:
        pickle.dump({"model_name": "some-other-model",
                     "entries": {"a": ("hi", np.array([1.0, 1.0]))}}, f)

    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts, **kwargs: np.array([[3.0, 3.0] for _ in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        result = index_worker.run(
            [NodeSnapshot("a", "hi")], "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    fake_model.encode.assert_called_once_with(["hi"], use_multiprocessing=False)
    assert np.array_equal(result.embeddings["a"], np.array([3.0, 3.0]))


def test_run_returns_embeddings_when_cache_write_fails(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts, **kwargs: np.array([[float(len(t)), 0.0] for t in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        with patch.object(index_worker.pickle, "dump", side_effect=OSError("disk full")):
            result = index_worker.run(
                [NodeSnapshot("a", "hi"), NodeSnapshot("b", "hello")],
                "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    assert set(result.embeddings.keys()) == {"a", "b"}
    assert np.array_equal(result.embeddings["a"], np.array([2.0, 0.0]))
    assert np.array_equal(result.embeddings["b"], np.array([5.0, 0.0]))


def test_run_treats_non_dict_cache_contents_as_missing_cache(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    with open(cache_path, "wb") as f:
        pickle.dump(["not", "a", "dict"], f)

    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts, **kwargs: np.array([[3.0, 3.0] for _ in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        result = index_worker.run(
            [NodeSnapshot("a", "hi")], "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    fake_model.encode.assert_called_once_with(["hi"], use_multiprocessing=False)
    assert np.array_equal(result.embeddings["a"], np.array([3.0, 3.0]))


def test_run_builds_bm25_index_reflecting_current_snapshot(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts, **kwargs: np.array([[1.0, 0.0] for _ in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        result = index_worker.run(
            [NodeSnapshot("mms1 fgm", "mms1 fgm"), NodeSnapshot("goes mag", "goes mag")],
            "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    scores = bm25_index.score(result.bm25, "mms1")
    assert scores["mms1 fgm"] > 0
    assert "goes mag" not in scores
