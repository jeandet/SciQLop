"""Pure logic of the sciqlop_fetch tool (fetch/scrub/grid/bind/summary).

Importing anything under `SciQLop.components.agents.tools` pulls in the agents
package `__init__` → chat_dock → _builder → ProductsModel, which needs a
QApplication. So each test takes pytest-qt's `qtbot` and imports inside the
function, matching tests/test_literature_tools.py. The fetch *logic* itself is
still exercised offline via injected fake backends.
"""
import numpy as np


class FakeVar:
    def __init__(self, name, values, times, unit="nT"):
        self.name = name
        self.values = np.asarray(values, dtype=float)
        self.time = np.asarray(times)
        self.unit = unit
        self.columns = [name] if self.values.ndim == 1 else [f"{name}{i}" for i in range(self.values.shape[1])]

    @property
    def shape(self):
        return self.values.shape

    def replace_fillval_by_nan(self, inplace=True, convert_to_float=True):
        return self

    def to_dataframe(self):  # only referenced by the bridges footer text
        import pandas as pd
        return pd.DataFrame(self.values)


def _times(n):
    return np.arange(n).astype("datetime64[s]")


def test_to_epoch_accepts_iso_and_number(qtbot):
    from SciQLop.components.agents.tools.fetch import to_epoch
    assert to_epoch(100) == 100.0
    assert to_epoch("1970-01-01T00:01:40+00:00") == 100.0


def test_cadence_seconds(qtbot):
    from SciQLop.components.agents.tools.fetch import cadence_seconds
    assert cadence_seconds("1min") == 60.0
    assert cadence_seconds("5s") == 5.0
    assert cadence_seconds("1h") == 3600.0


def test_fetch_single_binds_dict_and_summarizes(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    var = FakeVar("B_gse", [1.0, 2.0, np.nan, 4.0], _times(4))
    out = fetch_products(
        ["amda/b_gse"], 0.0, 4.0, "BUILD", ns,
        cadence=None, overwrite=False,
        fetch_one=lambda pid, t0, t1: [var],
        grid_interpolate=lambda ref, v: v,
    )
    assert set(ns["BUILD"].keys()) == {"B_gse"}
    text = out["content"][0]["text"]
    assert "BUILD" in text and "B_gse" in text and "nT" in text
    assert "coverage 75" in text  # 3 of 4 finite
    assert "to_dataframe()" in text  # bridges footer


def test_fetch_duplicate_name_gets_suffix(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    var1 = FakeVar("B", [1.0], _times(1))
    var2 = FakeVar("B", [2.0], _times(1))
    fetch_products(["p1", "p2"], 0.0, 1.0, "X", ns,
                   cadence=None, overwrite=False,
                   fetch_one=lambda pid, t0, t1: [var1 if pid == "p1" else var2],
                   grid_interpolate=lambda ref, v: v)
    assert set(ns["X"].keys()) == {"B", "B_2"}
