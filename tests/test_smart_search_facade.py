from unittest.mock import MagicMock
import pytest


@pytest.fixture(autouse=True)
def reset_facade_singleton():
    import SciQLop.components.smart_search as facade
    facade._registry = None
    yield
    facade._registry = None


def test_is_available_reflects_fastembed_importability():
    from SciQLop.components.smart_search import is_available
    assert is_available() is True  # fastembed is a mandatory dependency, always importable


def test_available_models_matches_settings_module():
    from SciQLop.components.smart_search import available_models
    from SciQLop.components.smart_search.settings import AVAILABLE_MODELS
    assert available_models() == list(AVAILABLE_MODELS)


def test_register_domain_and_query_delegate_to_registry(qtbot, monkeypatch, tmp_path):
    import SciQLop.components.smart_search as facade
    monkeypatch.setattr(facade, "_jobs_backend_instance", lambda: MagicMock())

    fake_registry = MagicMock()
    fake_registry.query.return_value = {"a": 42.0}
    monkeypatch.setattr(facade, "_get_registry", lambda: fake_registry)

    domain = MagicMock(name="products")
    facade.register_domain(domain)
    facade.unregister_domain("products")
    facade.notify_changed("products")
    result = facade.query("products", "hi")

    fake_registry.register_domain.assert_called_once_with(domain)
    fake_registry.unregister_domain.assert_called_once_with("products")
    fake_registry.notify_changed.assert_called_once_with("products")
    assert result == {"a": 42.0}


def test_get_model_and_set_model_read_and_write_settings(tmp_path, monkeypatch):
    from unittest.mock import patch
    with patch("SciQLop.components.settings.backend.entry.SCIQLOP_CONFIG_DIR", str(tmp_path)):
        from SciQLop.components.smart_search import get_model, set_model
        assert get_model() == "BAAI/bge-small-en-v1.5"
        set_model("sentence-transformers/all-MiniLM-L6-v2")
        assert get_model() == "sentence-transformers/all-MiniLM-L6-v2"
