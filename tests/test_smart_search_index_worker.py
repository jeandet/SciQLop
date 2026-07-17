from unittest.mock import patch, MagicMock
import numpy as np

from SciQLop.components.smart_search import index_worker
from SciQLop.components.smart_search.domain import NodeSnapshot


def test_run_embeds_every_node_and_keys_by_path():
    fake_model = MagicMock()
    fake_model.embed.side_effect = lambda texts: iter([np.array([float(len(t)), 0.0]) for t in texts])

    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model) as mock_load:
        result = index_worker.run(
            [NodeSnapshot("a", "hi"), NodeSnapshot("b", "hello")],
            "BAAI/bge-small-en-v1.5", "/tmp/cache")

    mock_load.assert_called_once_with("BAAI/bge-small-en-v1.5", "/tmp/cache")
    assert set(result.keys()) == {"a", "b"}
    assert np.array_equal(result["a"], np.array([2.0, 0.0]))
    assert np.array_equal(result["b"], np.array([5.0, 0.0]))


def test_run_with_empty_snapshot_returns_empty_dict():
    fake_model = MagicMock()
    with patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        result = index_worker.run([], "BAAI/bge-small-en-v1.5", "/tmp/cache")
    assert result == {}
