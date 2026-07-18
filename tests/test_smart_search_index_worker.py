from unittest.mock import patch, MagicMock
import pickle
import numpy as np

from SciQLop.components.smart_search import index_worker
from SciQLop.components.smart_search.domain import NodeSnapshot


def test_run_embeds_every_node_when_cache_empty(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts: np.array([[float(len(t)), 0.0] for t in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model) as mock_load:
        result = index_worker.run(
            [NodeSnapshot("a", "hi"), NodeSnapshot("b", "hello")],
            "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    mock_load.assert_called_once_with("minishlab/potion-base-8M", "/tmp/cache")
    assert set(result.keys()) == {"a", "b"}
    assert np.array_equal(result["a"], np.array([2.0, 0.0]))
    assert np.array_equal(result["b"], np.array([5.0, 0.0]))


def test_run_with_empty_snapshot_returns_empty_dict_and_writes_empty_cache(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    with patch.object(index_worker.model_fetch, "load_model") as mock_load:
        result = index_worker.run([], "minishlab/potion-base-8M", "/tmp/cache", cache_path)
    mock_load.assert_not_called()
    assert result == {}
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
    assert np.array_equal(result["a"], cached_vec)


def test_run_only_embeds_changed_entries_and_carries_unchanged_ones_through(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    cached_vec = np.array([9.0, 9.0])
    with open(cache_path, "wb") as f:
        pickle.dump({"model_name": "minishlab/potion-base-8M",
                     "entries": {"a": ("hi", cached_vec), "b": ("old text", np.array([1.0, 1.0]))}}, f)

    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts: np.array([[5.0, 5.0] for _ in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        result = index_worker.run(
            [NodeSnapshot("a", "hi"), NodeSnapshot("b", "new text")],
            "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    fake_model.encode.assert_called_once_with(["new text"])
    assert np.array_equal(result["a"], cached_vec)
    assert np.array_equal(result["b"], np.array([5.0, 5.0]))


def test_run_drops_entries_no_longer_in_current_snapshot(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    with open(cache_path, "wb") as f:
        pickle.dump({"model_name": "minishlab/potion-base-8M",
                     "entries": {"a": ("hi", np.array([1.0, 1.0])), "b": ("bye", np.array([2.0, 2.0]))}}, f)

    with patch.object(index_worker.model_fetch, "load_model") as mock_load:
        result = index_worker.run(
            [NodeSnapshot("a", "hi")], "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    mock_load.assert_not_called()
    assert set(result.keys()) == {"a"}


def test_run_discards_whole_cache_on_model_mismatch(tmp_path):
    cache_path = str(tmp_path / "cache.pkl")
    with open(cache_path, "wb") as f:
        pickle.dump({"model_name": "some-other-model",
                     "entries": {"a": ("hi", np.array([1.0, 1.0]))}}, f)

    fake_model = MagicMock()
    fake_model.encode.side_effect = lambda texts: np.array([[3.0, 3.0] for _ in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        result = index_worker.run(
            [NodeSnapshot("a", "hi")], "minishlab/potion-base-8M", "/tmp/cache", cache_path)

    fake_model.encode.assert_called_once_with(["hi"])
    assert np.array_equal(result["a"], np.array([3.0, 3.0]))
