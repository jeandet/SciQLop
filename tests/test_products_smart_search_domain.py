from unittest.mock import MagicMock, patch

from SciQLop.components.smart_search.domain import NodeSnapshot


def test_snapshot_wraps_corpus_snapshot_items():
    import SciQLop.components.products.smart_search_domain as mod

    fake_flat_model = MagicMock()
    fake_flat_model.corpus_snapshot.return_value = {"a": "text a", "b": "text b"}

    with patch.object(mod, "ProductsFlatFilterModel", return_value=fake_flat_model), \
         patch.object(mod, "ProductsModel") as mock_products_model:
        mock_products_model.instance.return_value = MagicMock()
        domain = mod.ProductsDomain()
        result = list(domain.snapshot())

    assert domain.name == "products"
    assert set(result) == {NodeSnapshot("a", "text a"), NodeSnapshot("b", "text b")}


def test_domain_notifies_registry_on_products_model_changes():
    import SciQLop.components.products.smart_search_domain as mod

    fake_products_model = MagicMock()
    with patch.object(mod, "ProductsFlatFilterModel", return_value=MagicMock()), \
         patch.object(mod, "ProductsModel") as mock_products_model, \
         patch.object(mod, "notify_changed") as mock_notify:
        mock_products_model.instance.return_value = fake_products_model
        mod.ProductsDomain()

        fake_products_model.rowsInserted.connect.assert_called_once()
        fake_products_model.rowsRemoved.connect.assert_called_once()
        fake_products_model.modelReset.connect.assert_called_once()

        on_changed = fake_products_model.rowsInserted.connect.call_args[0][0]
        on_changed()
    mock_notify.assert_called_once_with("products")


def test_register_smart_search_domain_registers_with_facade():
    import SciQLop.components.products.smart_search_domain as mod

    with patch.object(mod, "ProductsFlatFilterModel", return_value=MagicMock()), \
         patch.object(mod, "ProductsModel") as mock_products_model, \
         patch.object(mod, "register_domain") as mock_register:
        mock_products_model.instance.return_value = MagicMock()
        mod.register_smart_search_domain()

    mock_register.assert_called_once()
    registered = mock_register.call_args[0][0]
    assert isinstance(registered, mod.ProductsDomain)
