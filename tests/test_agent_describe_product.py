import numpy as np


class FakeIndex:
    """Stand-in for a speasy ParameterIndex. spz_* are methods; other
    attributes mimic raw provider metadata."""
    def __init__(self, name="", uid="", provider="", **attrs):
        self._name, self._uid, self._prov = name, uid, provider
        for k, v in attrs.items():
            setattr(self, k, v)

    def spz_name(self):
        return self._name

    def spz_uid(self):
        return self._uid

    def spz_provider(self):
        return self._prov


def _cda_index():
    return FakeIndex(
        name="cnt_Al", uid="AC_H2_CRIS/cnt_Al", provider="cda",
        UNITS="Counts/hour", FILLVAL=[-9.99e30], spz_shape=(7,),
        LABL_PTR_1=["cnt_Al 85.3-111.5", "cnt_Al 114.1-155.9"],
        CATDESC="Al counts at 7 energies", cdf_type="CDF_REAL4",
        dataset="AC_H2_CRIS", start_date="1997-08-27 00:00:00",
        stop_date="2026-06-11 23:00:00",
    )


def _amda_index():
    return FakeIndex(
        name="imf_gsm", uid="imf_gsm", provider="amda",
        units="nT", dim_1=1, dim_2=1, size=3, display_type="timeseries",
    )


def test_describe_cda_normalized_fields(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    out = describe_product(
        "cda/AC_H2_CRIS/cnt_Al", resolve_index=lambda p: (_cda_index(), None),
        probe_fetch=lambda *a: None)
    text = out["content"][0]["text"]
    assert "cnt_Al" in text and "cda" in text
    assert "Counts/hour" in text                 # units
    assert "-9.99e+30" in text or "-9.99e30" in text  # fillval surfaced
    assert "(7,)" in text                        # shape
    assert "2026-06-11" in text                  # coverage stop
    assert "cdf_type" in text                    # raw passthrough


def test_describe_amda_sparse_omits_absent_fields(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    out = describe_product(
        "amda/imf_gsm", resolve_index=lambda p: (_amda_index(), None),
        probe_fetch=lambda *a: None)
    text = out["content"][0]["text"]
    assert "imf_gsm" in text and "nT" in text
    assert "FILLVAL" not in text and "fillval" not in text.lower()  # absent → omitted
    assert "display_type" in text                # raw passthrough


def test_describe_unresolved_product_reports_cleanly(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    out = describe_product(
        "nope//bad", resolve_index=lambda p: (None, "product not found: nope//bad"),
        probe_fetch=lambda *a: None)
    assert "product not found" in out["content"][0]["text"]


class FakeVar:
    def __init__(self, values, times, meta=None, fill_value=None):
        self.values = np.asarray(values, dtype=float)
        self.time = np.asarray(times)
        self.meta = meta or {}
        self.fill_value = fill_value


def _sec_times(n, step_s=60):
    return (np.arange(n) * step_s).astype("datetime64[s]")


def test_probe_adds_real_shape_frame_and_gap_fraction(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    var = FakeVar([[1.0, 2.0, 3.0], [1.0, np.nan, 3.0]], _sec_times(2),
                  meta={"COORDINATE_SYSTEM": "gse"}, fill_value=-1e31)
    out = describe_product(
        "cda/AC_H2_CRIS/cnt_Al", probe=True, start=0, stop=120,
        resolve_index=lambda p: (_cda_index(), None),
        probe_fetch=lambda index, t0, t1: var)
    text = out["content"][0]["text"]
    assert "probe" in text
    assert "(2, 3)" in text            # real sampled shape
    assert "gse" in text               # coordinate frame from meta
    assert "-1e+31" in text or "-1e31" in text   # real fillval
    # one NaN of six values → ~16.7% gap
    assert "16.7" in text or "16.67" in text


def test_probe_default_window_used_when_no_start_stop(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    seen = {}

    def fetch(index, t0, t1):
        seen["t0"], seen["t1"] = t0, t1
        return FakeVar([1.0], _sec_times(1))

    describe_product(
        "cda/x", probe=True,
        resolve_index=lambda p: (_cda_index(), None),  # stop_date 2026-06-11 23:00:00
        probe_fetch=fetch)
    # default window is 24h ending at stop_date → 86400 s wide
    assert seen and (seen["t1"] - seen["t0"]) == 86400.0


def test_probe_median_cadence_handles_epoch_seconds_time(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product
    times = np.array([0.0, 60.0, 120.0, 180.0])  # already epoch seconds, not datetime64
    var = FakeVar([1.0, 2.0, 3.0, 4.0], times)
    out = describe_product(
        "cda/x", probe=True, start=0, stop=180,
        resolve_index=lambda p: (_cda_index(), None),
        probe_fetch=lambda index, t0, t1: var)
    assert "median_cadence_s**: 60.0" in out["content"][0]["text"]


def test_probe_failure_falls_back_to_metadata(qtbot):
    from SciQLop.components.agents.tools.describe import describe_product

    def boom(index, t0, t1):
        raise ValueError("provider 502")

    out = describe_product(
        "cda/x", probe=True, start=0, stop=120,
        resolve_index=lambda p: (_cda_index(), None),
        probe_fetch=boom)
    text = out["content"][0]["text"]
    assert "probe failed" in text and "cnt_Al" in text   # metadata still present
