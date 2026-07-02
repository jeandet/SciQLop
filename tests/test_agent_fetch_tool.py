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


def test_cadence_aligns_all_products_on_shared_ref(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    seen_refs = []

    def grid(ref, v):
        seen_refs.append(len(ref))
        return FakeVar(v.name, np.ones(len(ref)), ref)

    fetch_products(
        ["p1", "p2"], 0.0, 60.0, "G", ns,
        cadence="10s", overwrite=False,
        fetch_one=lambda pid, t0, t1: [FakeVar(pid, [1.0, 2.0], _times(2))],
        grid_interpolate=grid,
    )
    assert set(ns["G"].keys()) == {"p1", "p2"}
    assert seen_refs and len(set(seen_refs)) == 1        # every product hit the SAME grid
    assert ns["G"]["p1"].time.shape == ns["G"]["p2"].time.shape


def test_collision_without_overwrite_binds_nothing(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {"X": 123}
    out = fetch_products(["p"], 0.0, 1.0, "X", ns, cadence=None, overwrite=False,
                         fetch_one=lambda *a: [FakeVar("p", [1.0], _times(1))],
                         grid_interpolate=lambda r, v: v)
    assert ns["X"] == 123                                # untouched
    assert "already bound" in out["content"][0]["text"]


def test_overwrite_true_rebinds(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {"X": 123}
    fetch_products(["p"], 0.0, 1.0, "X", ns, cadence=None, overwrite=True,
                   fetch_one=lambda *a: [FakeVar("p", [1.0], _times(1))],
                   grid_interpolate=lambda r, v: v)
    assert isinstance(ns["X"], dict) and "p" in ns["X"]


def test_partial_failure_binds_good_reports_bad(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}

    def fetch_one(pid, t0, t1):
        if pid == "bad":
            raise ValueError("product not found")
        return [FakeVar("good", [1.0], _times(1))]

    out = fetch_products(["good_id", "bad"], 0.0, 1.0, "M", ns, cadence=None,
                         overwrite=False, fetch_one=fetch_one, grid_interpolate=lambda r, v: v)
    assert "good" in ns["M"]
    assert "bad: ValueError: product not found" in out["content"][0]["text"]


def test_all_fail_binds_nothing(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    out = fetch_products(["a", "b"], 0.0, 1.0, "M", ns, cadence=None, overwrite=False,
                         fetch_one=lambda *a: (_ for _ in ()).throw(ValueError("nope")),
                         grid_interpolate=lambda r, v: v)
    assert "M" not in ns
    assert out["content"][0]["text"].count("⚠️") == 2


def test_preview_appends_image_block(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    out = fetch_products(["p"], 0.0, 4.0, "P", ns, cadence=None, overwrite=False,
                         preview=True,
                         fetch_one=lambda *a: [FakeVar("B", [1.0, 2.0, 3.0, 4.0], _times(4))],
                         grid_interpolate=lambda r, v: v)
    kinds = [c["type"] for c in out["content"]]
    assert "image" in kinds
    img = next(c for c in out["content"] if c["type"] == "image")
    assert img["mimeType"] == "image/png" and img["data"]


def test_no_preview_by_default_is_text_only(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}
    out = fetch_products(["p"], 0.0, 1.0, "P", ns, cadence=None, overwrite=False,
                         fetch_one=lambda *a: [FakeVar("B", [1.0], _times(1))],
                         grid_interpolate=lambda r, v: v)
    assert [c["type"] for c in out["content"]] == ["text"]


def test_post_fetch_error_does_not_sink_batch(qtbot):
    from SciQLop.components.agents.tools.fetch import fetch_products
    ns = {}

    def grid(ref, v):
        if v.name == "bad":
            raise ValueError("cannot interpolate spectro")
        return v

    out = fetch_products(["good", "bad"], 0.0, 60.0, "M", ns, cadence="10s",
                         overwrite=False,
                         fetch_one=lambda pid, t0, t1: [FakeVar(pid, [1.0, 2.0], _times(2))],
                         grid_interpolate=grid)
    assert "good" in ns["M"] and "bad" not in ns["M"]
    assert "bad: ValueError: cannot interpolate spectro" in out["content"][0]["text"]
