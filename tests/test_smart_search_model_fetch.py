from unittest.mock import patch, MagicMock

from SciQLop.components.smart_search import model_fetch


def test_download_model_constructs_text_embedding_with_cache_dir(tmp_path):
    with patch.object(model_fetch, "TextEmbedding") as mock_cls:
        model_fetch.download_model("BAAI/bge-small-en-v1.5", str(tmp_path))
    mock_cls.assert_called_once_with(model_name="BAAI/bge-small-en-v1.5", cache_dir=str(tmp_path))


def test_load_model_uses_local_files_only(tmp_path):
    with patch.object(model_fetch, "TextEmbedding") as mock_cls:
        mock_cls.return_value = MagicMock()
        result = model_fetch.load_model("BAAI/bge-small-en-v1.5", str(tmp_path))
    mock_cls.assert_called_once_with(
        model_name="BAAI/bge-small-en-v1.5", cache_dir=str(tmp_path), local_files_only=True)
    assert result is mock_cls.return_value
