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
