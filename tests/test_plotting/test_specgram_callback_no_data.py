import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _isolate_products(qapp, monkeypatch):
    from SciQLop.core.models import products
    monkeypatch.setattr(products, "add_node", lambda *a, **k: None)


def _make_spectrogram(callback):
    from SciQLop.components.plotting.backend.easy_provider import EasySpectrogram
    return EasySpectrogram(path="vp/test_spec", get_data_callback=callback, metadata={})


def test_no_data_returns_empty_arrays_without_error_log(monkeypatch):
    """A callback returning None (no data in range) is a routine outcome, not
    a bug — it must not be logged at ERROR level via an unpack exception."""
    from SciQLop.components.plotting.ui import time_sync_panel
    from SciQLop.components.plotting.ui.time_sync_panel import _specgram_callback

    errors = []
    monkeypatch.setattr(time_sync_panel.log, "error", lambda *a, **k: errors.append(a))

    def f(start: float, stop: float):
        return None

    p = _make_spectrogram(f)
    cb = _specgram_callback(provider=p, node=None)

    x, y, z = cb(0.0, 1.0)

    assert x.size == 0 and y.size == 0 and z.size == 0
    assert errors == []


def test_fetch_raising_is_still_logged_and_returns_empty_arrays(monkeypatch):
    """If `_fetch` itself raises (e.g. provider._get_data blows up before it
    gets a chance to convert the error to []), it must still be surfaced at
    ERROR level — distinct from the routine "no data" case."""
    from SciQLop.components.plotting.ui import time_sync_panel
    from SciQLop.components.plotting.ui.time_sync_panel import _specgram_callback

    errors = []
    monkeypatch.setattr(time_sync_panel.log, "error", lambda *a, **k: errors.append(a))

    class _RaisingProvider:
        def _get_data(self, node, start, stop, on_variable=None, knobs=None):
            raise RuntimeError("boom")

    cb = _specgram_callback(provider=_RaisingProvider(), node=None)

    x, y, z = cb(0.0, 1.0)

    assert x.size == 0 and y.size == 0 and z.size == 0
    assert len(errors) == 1


def test_real_data_still_flows_through(monkeypatch):
    from SciQLop.components.plotting.ui import time_sync_panel
    from SciQLop.components.plotting.ui.time_sync_panel import _specgram_callback

    errors = []
    monkeypatch.setattr(time_sync_panel.log, "error", lambda *a, **k: errors.append(a))

    def f(start: float, stop: float):
        x = np.linspace(start, stop, 4)
        y = np.array([1.0, 2.0, 3.0])
        z = np.zeros((4, 3))
        return x, y, z

    p = _make_spectrogram(f)
    cb = _specgram_callback(provider=p, node=None)

    x, y, z = cb(0.0, 1.0)

    assert x.shape == (4,)
    assert y.shape == (3,)
    assert z.shape == (4, 3)
    assert errors == []
