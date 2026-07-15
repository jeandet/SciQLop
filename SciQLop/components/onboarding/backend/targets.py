from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex
from PySide6.QtWidgets import QTreeView, QWidget

CANDIDATE_PRODUCT_PATHS: list[list[str]] = [
    ["cda", "MMS", "MMS1", "FGM", "mms1_fgm_b_gse_srvy_l2"],
    ["cda", "THEMIS", "THA", "FGM", "tha_fgs_gse"],
    ["amda", "Parameters", "Clusters", "Cluster1", "Ephemeris", "c1_xyz_gse"],
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


def resolve_products_tree_widget(main_window, context) -> QWidget | None:
    return _products_tree_view(main_window)
