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


def test_resolve_catalog_tree_finds_a_tree_view(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_catalog_tree
    from PySide6.QtWidgets import QTreeView
    result = resolve_catalog_tree(main_window, {})
    assert isinstance(result, QTreeView)


def test_resolve_add_event_button_matches_visibility_state(main_window):
    """Doesn't assert a specific None/not-None outcome: main_window is a
    session-scoped fixture shared with unrelated test files, so whether a
    catalog happens to be selected elsewhere in the session isn't this
    test's business. What must always hold is the function's own contract:
    it never returns a hidden button."""
    from SciQLop.components.onboarding.backend.targets import resolve_add_event_button
    result = resolve_add_event_button(main_window, {})
    if result is not None:
        assert result.isVisible()


def test_resolve_any_plot_with_data_returns_none_when_no_plots():
    from SciQLop.components.onboarding.backend.targets import resolve_any_plot_with_data
    from unittest.mock import MagicMock

    fake_main_window = MagicMock()
    fake_main_window.plot_panels.return_value = []
    assert resolve_any_plot_with_data(fake_main_window, {}) is None


def test_resolve_any_plot_with_data_returns_last_plot_of_a_panel_with_plots():
    from SciQLop.components.onboarding.backend.targets import resolve_any_plot_with_data
    from unittest.mock import MagicMock

    fake_widget = object()
    fake_panel = MagicMock()
    fake_panel.plots.return_value = [fake_widget]
    fake_main_window = MagicMock()
    fake_main_window.plot_panels.return_value = ["panel1"]
    fake_main_window.plot_panel.return_value = fake_panel
    assert resolve_any_plot_with_data(fake_main_window, {}) is fake_widget


def test_resolve_settings_category_list_finds_a_list_view(main_window):
    from SciQLop.components.onboarding.backend.targets import resolve_settings_category_list
    from PySide6.QtWidgets import QListView
    result = resolve_settings_category_list(main_window, {})
    assert isinstance(result, QListView)
