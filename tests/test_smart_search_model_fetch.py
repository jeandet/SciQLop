from unittest.mock import patch, MagicMock

from SciQLop.components.smart_search import model_fetch


def test_download_model_fetches_snapshot_with_cache_dir(tmp_path):
    with patch("huggingface_hub.snapshot_download") as mock_download:
        model_fetch.download_model("minishlab/potion-base-8M", str(tmp_path))
    mock_download.assert_called_once_with(repo_id="minishlab/potion-base-8M", cache_dir=str(tmp_path))


def test_load_model_resolves_local_snapshot_then_loads_offline(tmp_path):
    with patch("huggingface_hub.snapshot_download", return_value="/local/snapshot/path") as mock_download, \
         patch("model2vec.StaticModel.from_pretrained") as mock_from_pretrained:
        mock_from_pretrained.return_value = MagicMock()
        result = model_fetch.load_model("minishlab/potion-base-8M", str(tmp_path))
    mock_download.assert_called_once_with(
        repo_id="minishlab/potion-base-8M", cache_dir=str(tmp_path), local_files_only=True)
    mock_from_pretrained.assert_called_once_with("/local/snapshot/path", force_download=False)
    assert result is mock_from_pretrained.return_value
