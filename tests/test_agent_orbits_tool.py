"""Pure logic of the ephemeris/transform tools (time helpers + rendering).

Importing anything under `SciQLop.components.agents.tools` needs a
QApplication (agents package __init__ -> chat_dock -> _builder ->
ProductsModel), so every test takes pytest-qt's `qtbot` and imports inside
the function, matching tests/test_agent_fetch_tool.py.
"""


def test_to_epoch_accepts_iso_and_number(qtbot):
    from SciQLop.components.agents.tools.orbits import _to_epoch
    assert _to_epoch(100) == 100.0
    assert _to_epoch("1970-01-01T00:01:40+00:00") == 100.0


def test_epoch_to_3dview_formats_milliseconds(qtbot):
    from SciQLop.components.agents.tools.orbits import _epoch_to_3dview
    assert _epoch_to_3dview(1577836800.0) == "2020-01-01T00:00:00.000"


def test_iso_to_ns_strips_trailing_z(qtbot):
    import numpy as np
    from SciQLop.components.agents.tools.orbits import _iso_to_ns
    assert _iso_to_ns("2026-01-01T00:00:00.000Z") == np.datetime64("2026-01-01T00:00:00.000", "ns")


def test_check_overwrite_blocks_existing_name(qtbot):
    from SciQLop.components.agents.tools.orbits import _check_overwrite
    out = _check_overwrite("X", {"X": 123}, overwrite=False)
    assert out is not None
    assert "already bound" in out["content"][0]["text"]


def test_check_overwrite_allows_when_flag_set_or_name_free(qtbot):
    from SciQLop.components.agents.tools.orbits import _check_overwrite
    assert _check_overwrite("X", {"X": 123}, overwrite=True) is None
    assert _check_overwrite("Y", {"X": 123}, overwrite=False) is None


def test_time_range_params_includes_sampling_only_when_given(qtbot):
    from SciQLop.components.agents.tools.orbits import _time_range_params
    p = _time_range_params(1577836800.0, 1577840400.0, None)
    assert p["format"] == "json"
    assert p["start"] == "2020-01-01T00:00:00.000"
    assert p["stop"] == "2020-01-01T01:00:00.000"
    assert "sampling" not in p
    p2 = _time_range_params(1577836800.0, 1577840400.0, 600)
    assert p2["sampling"] == "600"


_BODIES_PAYLOAD = {"bodies": [
    {"id": -144, "name": "Solar Orbiter", "coverage": ["2020-02-10T04:55:49.670Z", "2030-11-20T04:42:43.611Z"], "type": "SPACECRAFT"},
    {"id": 399, "name": "Earth", "coverage": ["1900-01-01T00:00:00.000Z", "2200-01-01T00:00:00.000Z"], "type": "PLANET"},
]}
_FRAMES_PAYLOAD = {"frames": [
    {"id": 1, "name": "J2000", "desc": "Earth mean equator, dynamical equinox of J2000", "center": "Sun"},
    {"id": 1601010, "name": "HEEQ", "desc": "Heliocentric Earth Equatorial", "center": "Sun"},
]}


def test_render_bodies_and_frames_lists_both_sorted_and_described(qtbot):
    from SciQLop.components.agents.tools.orbits import render_bodies_and_frames
    text = render_bodies_and_frames(_BODIES_PAYLOAD, _FRAMES_PAYLOAD)
    assert "### bodies (2)" in text
    assert "Earth, Solar Orbiter" in text  # sorted alphabetically
    assert "### frames (2)" in text
    assert "`HEEQ` — Heliocentric Earth Equatorial" in text


def test_bodies_and_frames_impl_calls_both_endpoints_and_renders(qtbot, monkeypatch):
    """Tests `_bodies_and_frames_impl` directly (NOT the cached `bodies_and_frames`
    wrapper) by monkeypatching orbits.http.get — this sidesteps speasy's
    disk-persistent CacheCall cache entirely, so the test is not flaky across
    runs (the cached wrapper has no args to key on, so any test that exercised
    it through the real cache would read stale results from a prior run)."""
    import SciQLop.components.agents.tools.orbits as orbits

    calls = []

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if url.endswith("/get_bodies"):
            return _Resp(_BODIES_PAYLOAD)
        return _Resp(_FRAMES_PAYLOAD)

    monkeypatch.setattr(orbits.http, "get", fake_get)
    text = orbits._bodies_and_frames_impl()
    assert "Earth, Solar Orbiter" in text
    assert len(calls) == 2
    assert calls[0].endswith("/get_bodies") and calls[1].endswith("/get_frames")
