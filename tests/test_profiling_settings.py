from SciQLop.components.profiling.settings import ProfilingSettings


def test_defaults_match_documented_values():
    s = ProfilingSettings()
    assert s.sampler_enabled is False
    assert s.sample_interval_ms == 200
    assert s.watchdog_enabled is True
    assert s.watchdog_stall_threshold_s == 3.0
    assert s.watchdog_severe_threshold_s == 10.0
