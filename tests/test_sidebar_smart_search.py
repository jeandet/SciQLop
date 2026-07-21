"""Tests for wiring SciQLopPlots' ProductsView (the sidebar Products
browser) to components/smart_search/ -- the counterpart of
test_product_search_overlay.py's smart-search coverage, but for the sidebar
tree instead of the empty-panel popup. See docs/superpowers/specs/
2026-07-21-productsview-score-passthrough-design.md."""
import uuid
from unittest.mock import patch

import shiboken6
from PySide6.QtCore import QCoreApplication, QThreadPool
from PySide6.QtWidgets import QListView, QTextEdit

from SciQLopPlots import (
    ProductsFlatFilterModel, ProductsModel, ProductsModelNode,
    ProductsModelNodeType, ParameterType, ProductsView,
)

import SciQLop.components.products.sidebar_smart_search as mod


def _flush(qtbot):
    qtbot.wait(200)  # ProductsView's query bar debounces free_text_query_changed
    for _ in range(10):
        QCoreApplication.processEvents()


def _list_view_model(view):
    return next(
        lv.model() for lv in view.findChildren(QListView)
        if isinstance(lv.model(), ProductsFlatFilterModel))


def _visible_names(model):
    return [model.data(model.index(i, 0)) for i in range(model.rowCount())]


class TestSidebarSmartSearchWiring:
    def test_query_changed_dispatches_and_scores_surface_a_match(self, qtbot):
        token = uuid.uuid4().hex[:8]
        model = ProductsModel.instance()
        root = ProductsModelNode(f"SidebarSmartSearchRoot_{token}")
        leaf = ProductsModelNode(
            "acronym_only", "test", {"description": "totally unrelated text"},
            ProductsModelNodeType.PARAMETER, ParameterType.Scalar)
        root.add_child(leaf)
        model.add_node([], root)
        path_key = " ".join(leaf.path())

        view = ProductsView()
        qtbot.addWidget(view)
        mod.setup_sidebar_smart_search(view)

        with patch.object(mod.smart_search, "is_enabled", return_value=True), \
             patch.object(mod.smart_search, "query",
                           return_value={path_key: 100.0}) as mock_query:
            view.findChild(QTextEdit).setPlainText("magnetic field")
            _flush(qtbot)

        mock_query.assert_called_once_with("products", "magnetic field")
        assert "acronym_only" in _visible_names(_list_view_model(view))

    def test_not_dispatched_when_smart_search_disabled(self, qtbot):
        view = ProductsView()
        qtbot.addWidget(view)
        mod.setup_sidebar_smart_search(view)

        with patch.object(mod.smart_search, "is_enabled", return_value=False), \
             patch.object(mod.smart_search, "query") as mock_query:
            view.findChild(QTextEdit).setPlainText("magnetic field")
            _flush(qtbot)

        mock_query.assert_not_called()

    def test_clearing_query_disables_the_signal(self, qtbot):
        view = ProductsView()
        qtbot.addWidget(view)
        mod.setup_sidebar_smart_search(view)

        with patch.object(mod.smart_search, "is_enabled", return_value=True), \
             patch.object(mod.smart_search, "query", return_value={}):
            bar = view.findChild(QTextEdit)
            bar.setPlainText("magnetic field")
            _flush(qtbot)
            assert view.signal_enabled("smart_search") is True

            bar.setPlainText("")
            _flush(qtbot)
            assert view.signal_enabled("smart_search") is False

    def test_scores_not_applied_when_view_destroyed(self, qtbot):
        view = ProductsView()
        qtbot.addWidget(view)
        mod.setup_sidebar_smart_search(view)

        errors = []

        def run_inline(runnable):
            try:
                runnable.run()
            except Exception as exc:
                errors.append(exc)

        with patch.object(mod.smart_search, "is_enabled", return_value=True), \
             patch.object(mod.smart_search, "query", return_value={"a": 99.0}), \
             patch.object(shiboken6, "isValid", return_value=False), \
             patch.object(QThreadPool.globalInstance(), "start", side_effect=run_inline):
            view.findChild(QTextEdit).setPlainText("magnetic field")
            _flush(qtbot)

        assert errors == []
