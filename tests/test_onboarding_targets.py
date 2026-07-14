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
