from unittest.mock import MagicMock
from PySide6.QtCore import Qt


def _fake_model(tree: dict):
    """Build a minimal QAbstractItemModel-like mock from a nested dict,
    e.g. {"cda": {"MMS": {"MMS1": {}}}}."""
    model = MagicMock()

    def index(row, col, parent):
        children = _children_of(parent)
        idx = MagicMock()
        idx.isValid.return_value = True
        idx.row.return_value = row
        idx.internalPointer.return_value = children[row][0] if row < len(children) else None
        idx._node = children[row][1] if row < len(children) else None
        idx._name = children[row][0] if row < len(children) else None
        return idx

    def _children_of(parent):
        node = tree if parent is None or not parent.isValid() else getattr(parent, "_node", tree)
        return list(node.items())

    def row_count(parent):
        return len(_children_of(parent))

    def data(idx, role):
        if role == Qt.ItemDataRole.DisplayRole:
            return idx._name
        return None

    model.index.side_effect = index
    model.rowCount.side_effect = row_count
    model.data.side_effect = data
    return model


def test_find_index_by_path_found():
    from SciQLop.components.onboarding.backend.targets import find_index_by_path
    model = _fake_model({"cda": {"MMS": {"MMS1": {}}}})
    result = find_index_by_path(model, ["cda", "MMS", "MMS1"])
    assert result is not None
    assert result._name == "MMS1"


def test_find_index_by_path_not_found():
    from SciQLop.components.onboarding.backend.targets import find_index_by_path
    model = _fake_model({"cda": {"MMS": {}}})
    assert find_index_by_path(model, ["cda", "AMDA", "whatever"]) is None


def test_find_index_by_path_case_insensitive():
    from SciQLop.components.onboarding.backend.targets import find_index_by_path
    model = _fake_model({"CDA": {"mms": {}}})
    result = find_index_by_path(model, ["cda", "MMS"])
    assert result is not None
    assert result._name == "mms"


from .fixtures import *


def test_resolve_add_panel_button_accepts_context_arg(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button
    # Must not raise TypeError for the extra positional arg.
    resolve_add_panel_button(main_window, {})


def test_resolve_products_tree_widget_accepts_context_arg(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_products_tree_widget
    resolve_products_tree_widget(main_window, {})


def test_resolve_first_candidate_product_accepts_context_arg(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_first_candidate_product
    resolve_first_candidate_product(main_window, {})


def test_resolve_latest_plot_widget_reads_panel_from_context(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_latest_plot_widget
    assert resolve_latest_plot_widget(main_window, {}) is None

    fake_panel = type("FakePanel", (), {"plots": lambda self: []})()
    assert resolve_latest_plot_widget(main_window, {"create_panel": fake_panel}) is None

    fake_widget = object()
    fake_panel_with_plot = type("FakePanel", (), {"plots": lambda self: [fake_widget]})()
    assert resolve_latest_plot_widget(
        main_window, {"create_panel": fake_panel_with_plot}) is fake_widget


def test_side_tab_resolver_returns_none_for_missing_dock(main_window):
    from SciQLop.components.onboarding.backend.targets import side_tab_resolver
    assert side_tab_resolver("No Such Dock")(main_window, {}) is None


def test_side_tab_resolver_returns_products_side_tab(main_window):
    from SciQLop.components.onboarding.backend.targets import side_tab_resolver
    dw = main_window.dock_manager.findDockWidget("Products")
    assert side_tab_resolver("Products")(main_window, {}) is dw.sideTabWidget()
