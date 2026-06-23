import numpy as np


class _Shell:
    def __init__(self, ns):
        self.user_ns = ns

    def object_inspect(self, name, detail_level=0):
        if name in self.user_ns:
            return {"found": True, "type_name": type(self.user_ns[name]).__name__,
                    "string_form": repr(self.user_ns[name]), "docstring": ""}
        return {"found": False}


def test_kernel_vars_filters_and_summarizes(qtbot):
    from SciQLop.components.agents.tools.kernel import kernel_vars
    ns = {"x": 3, "arr": np.zeros((2, 3)), "_hidden": 1, "In": [], "Out": {},
          "get_ipython": lambda: None, "__name__": "__main__"}
    text = kernel_vars(_Shell(ns))
    assert "x" in text and "int" in text
    assert "arr" in text and "(2, 3)" in text         # ndarray shape summary
    assert "_hidden" not in text and "In" not in text and "get_ipython" not in text


def test_inspect_found_and_missing(qtbot):
    from SciQLop.components.agents.tools.kernel import inspect_name
    sh = _Shell({"x": 42})
    assert "int" in inspect_name(sh, "x")
    assert "not defined" in inspect_name(sh, "nope").lower()
