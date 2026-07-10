import sys
import threading
import time

from SciQLop.components.profiling import sampler as sampler_module
from SciQLop.components.profiling.sampler import Sampler


def _level3():
    return sys._getframe()


def _level2():
    return _level3()


def _level1():
    return _level2()


def test_summarize_frame_respects_depth_limit():
    frame = _level1()
    summary = sampler_module._summarize(frame, depth=2)
    assert len(summary) == 2
    assert "_level3" in summary[0]
    assert "_level2" in summary[1]


def test_sample_once_captures_current_thread():
    s = Sampler(interval_s=0.05, max_samples=100, frame_depth=2)
    s._sample_once()
    snap = s.snapshot()
    assert len(snap) >= 1
    assert any(sample.tid == threading.get_ident() for sample in snap)


def test_ring_buffer_caps_at_max_samples():
    s = Sampler(interval_s=0.01, max_samples=5, frame_depth=1)
    for _ in range(20):
        s._sample_once()
    assert len(s.snapshot()) <= 5


def test_clear_empties_the_buffer():
    s = Sampler(interval_s=0.05, max_samples=100, frame_depth=1)
    s._sample_once()
    assert s.snapshot()
    s.clear()
    assert s.snapshot() == []


def test_start_and_stop_background_thread():
    s = Sampler(interval_s=0.02, max_samples=1000, frame_depth=1)
    s.start()
    try:
        assert s.running
        deadline = time.monotonic() + 2
        while not s.snapshot() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert s.snapshot()
    finally:
        s.stop()
    assert not s.running


def test_start_is_idempotent():
    s = Sampler(interval_s=0.05, max_samples=100, frame_depth=1)
    s.start()
    try:
        first_thread = s._thread
        s.start()
        assert s._thread is first_thread
    finally:
        s.stop()


def test_get_sampler_returns_same_instance_and_respects_settings(monkeypatch):
    sampler_module._sampler = None
    from SciQLop.components.profiling.settings import ProfilingSettings
    monkeypatch.setattr(ProfilingSettings, "sampler_enabled", False, raising=False)

    s1 = sampler_module.get_sampler()
    s2 = sampler_module.get_sampler()
    assert s1 is s2

    sampler_module.maybe_start_from_settings()
    assert not s1.running  # sampler_enabled=False -> not started
    sampler_module._sampler = None


def test_flush_to_file_writes_reason_and_is_readable(tmp_path):
    s = Sampler(interval_s=0.05, max_samples=100, frame_depth=2)
    s._sample_once()
    path = sampler_module.flush_to_file(s, tmp_path, reason="unit-test")
    assert path.is_file()
    content = path.read_text()
    assert "unit-test" in content
    assert "test_flush_to_file_writes_reason_and_is_readable" in content
