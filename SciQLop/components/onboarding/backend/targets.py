from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex
from PySide6.QtWidgets import QTreeView, QWidget, QPushButton, QListView

CANDIDATE_PRODUCT_PATHS: list[list[str]] = [
    ["speasy", "amda", "Parameters", "ACE", "MFI", "final / prelim", "b_gse"],
]


def find_index_by_path(model: QAbstractItemModel, path: list[str],
                        parent: QModelIndex | None = None) -> QModelIndex | None:
    if not path:
        return parent
    parent = parent if parent is not None else QModelIndex()
    row_count = model.rowCount(parent)
    target = path[0].lower()
    for row in range(row_count):
        idx = model.index(row, 0, parent)
        text = model.data(idx, Qt.ItemDataRole.DisplayRole)
        if isinstance(text, str) and text.lower() == target:
            return find_index_by_path(model, path[1:], idx)
    return None


def _products_tree_view(main_window) -> QTreeView | None:
    trees = main_window.productTree.findChildren(QTreeView)
    return trees[0] if trees else None


def resolve_add_panel_button(main_window, context) -> QWidget | None:
    dw = next((dw for dw in main_window.dock_manager.dockWidgets()
               if dw.widget() is main_window.welcome), None)
    if dw is None:
        return None
    area = dw.dockAreaWidget()
    if area is None:
        return None
    return area.property("sciqlop_add_panel_button")


def side_tab_resolver(dock_name: str):
    def _resolver(main_window, context) -> QWidget | None:
        dw = main_window.dock_manager.findDockWidget(dock_name)
        if dw is None:
            return None
        return dw.sideTabWidget()
    return _resolver


def _expand_ancestors(tree: QTreeView, index: QModelIndex) -> None:
    parent = index.parent()
    chain = []
    while parent.isValid():
        chain.append(parent)
        parent = parent.parent()
    for ancestor in reversed(chain):
        tree.setExpanded(ancestor, True)


def resolve_first_candidate_product(main_window, context):
    """Returns (tree, rect) where rect is the matched row's visualRect in
    the tree's own local coordinates -- CoachMark highlights that sub-region
    of the tree widget rather than the whole tree."""
    tree = _products_tree_view(main_window)
    if tree is None:
        return None
    model = tree.model()
    if model is None:
        return None
    for path in CANDIDATE_PRODUCT_PATHS:
        index = find_index_by_path(model, path)
        if index is not None:
            _expand_ancestors(tree, index)
            tree.scrollTo(index)
            return tree, tree.visualRect(index)
    return None


def resolve_latest_plot_widget(main_window, context) -> QWidget | None:
    panel = context.get("create_panel")
    if panel is None:
        return None
    plots = panel.plots()
    return plots[-1] if plots else None


def resolve_panel_widget(main_window, context) -> QWidget | None:
    return context.get("create_panel")


def resolve_products_tree_widget(main_window, context) -> QWidget | None:
    return _products_tree_view(main_window)


def resolve_catalog_tree(main_window, context) -> QTreeView | None:
    trees = main_window.catalogs_browser.findChildren(QTreeView)
    return trees[0] if trees else None


def resolve_add_event_button(main_window, context) -> QWidget | None:
    for button in main_window.catalogs_browser.findChildren(QPushButton):
        if button.text() == "Add Event" and button.isVisible():
            return button
    return None


def resolve_catalogs_browser_widget(main_window, context) -> QWidget | None:
    return main_window.catalogs_browser


def resolve_any_plot_with_data(main_window, context) -> QWidget | None:
    for name in main_window.plot_panels():
        panel = main_window.plot_panel(name)
        if panel is None:
            continue
        plots = panel.plots()
        if plots:
            return plots[-1]
    return None


def resolve_settings_category_list(main_window, context) -> QListView | None:
    # Not findChildren(QListView)[0]: a setting's own dropdown delegate
    # (e.g. "Color Palette", a QComboBox) owns an internal QListView for
    # its popup -- a real, findable QObject even while closed, with a
    # leftover default geometry unrelated to anything on screen. Find
    # the intended widget by its object name, not "whichever QListView
    # happens to be found first".
    return main_window.settings_panel.findChild(QListView, "SettingsCategories")
