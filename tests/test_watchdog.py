import threading
import time

from SciQLop.components.profiling.watchdog import Watchdog, WatchdogState, suppressed


def _state(**overrides):
    kwargs = dict(stall_threshold_s=3.0, severe_threshold_s=10.0,
                  cooldown_s=5.0, max_dumps=20)
    kwargs.update(overrides)
    return WatchdogState(**kwargs)


def test_below_threshold_is_none():
    s = _state()
    action, info = s.check(now=100.0, last_heartbeat=99.0)  # 1s elapsed
    assert action == "none"


def test_first_crossing_of_stall_threshold_dumps_silently():
    s = _state()
    action, info = s.check(now=104.0, last_heartbeat=100.0)  # 4s elapsed
    assert action == "silent"
    assert info == 4.0


def test_repeated_checks_within_cooldown_do_not_redump():
    s = _state(cooldown_s=5.0)
    action1, _ = s.check(now=104.0, last_heartbeat=100.0)  # 4s -> silent
    action2, _ = s.check(now=106.0, last_heartbeat=100.0)  # 6s, +2s since dump -> none
    assert action1 == "silent"
    assert action2 == "none"


def test_redumps_after_cooldown_elapses_while_still_stalled():
    s = _state(cooldown_s=5.0)
    s.check(now=104.0, last_heartbeat=100.0)               # dump at t=104
    action, _ = s.check(now=110.0, last_heartbeat=100.0)   # 10s elapsed, but that's >= severe too
    # use a stall that never reaches severe to isolate the cooldown behavior
    s2 = _state(cooldown_s=5.0, severe_threshold_s=100.0)
    s2.check(now=104.0, last_heartbeat=100.0)
    action2, _ = s2.check(now=110.0, last_heartbeat=100.0)  # +6s since last dump, past cooldown
    assert action2 == "silent"


def test_severe_threshold_surfaces_even_within_cooldown_of_a_silent_dump():
    s = _state(stall_threshold_s=3.0, severe_threshold_s=10.0, cooldown_s=30.0)
    action1, _ = s.check(now=104.0, last_heartbeat=100.0)   # silent dump at 4s
    assert action1 == "silent"
    action2, _ = s.check(now=111.0, last_heartbeat=100.0)   # 11s -> severe, still within cooldown
    assert action2 == "surface"


def test_severe_only_fires_once_per_stall_episode():
    s = _state(severe_threshold_s=10.0, cooldown_s=1.0)
    s.check(now=111.0, last_heartbeat=100.0)  # severe fires
    action, _ = s.check(now=112.0, last_heartbeat=100.0)  # still severe range, cooldown elapsed
    assert action == "silent"  # not "surface" again


def test_heartbeat_resuming_clears_and_reports_duration():
    s = _state()
    s.check(now=104.0, last_heartbeat=100.0)   # stall starts ~t=100
    action, duration = s.check(now=105.0, last_heartbeat=105.0)  # heartbeat resumed
    assert action == "cleared"
    assert duration == 5.0


def test_new_stall_after_clear_can_dump_again_immediately():
    s = _state(cooldown_s=100.0)
    s.check(now=104.0, last_heartbeat=100.0)             # silent dump
    s.check(now=105.0, last_heartbeat=105.0)              # cleared
    action, _ = s.check(now=204.0, last_heartbeat=200.0)  # new stall, long after
    assert action == "silent"  # cooldown doesn't block a fresh stall episode


def test_max_dumps_cap_stops_further_dumps():
    s = _state(cooldown_s=0.0, max_dumps=2)
    a1, _ = s.check(now=104.0, last_heartbeat=100.0)
    a2, _ = s.check(now=105.0, last_heartbeat=100.0)
    a3, _ = s.check(now=106.0, last_heartbeat=100.0)
    assert [a1, a2, a3] == ["silent", "silent", "none"]


def test_suppressed_context_manager_is_reentrant_and_tracks_active():
    assert not suppressed().active
    with suppressed():
        assert suppressed().active
        with suppressed():
            assert suppressed().active
        assert suppressed().active
    assert not suppressed().active


def test_watchdog_heartbeat_and_manual_check_end_to_end(tmp_path, monkeypatch):
    from SciQLop.components.profiling import hang_dump, sampler as sampler_module
    monkeypatch.setattr(hang_dump, "default_directory", lambda: tmp_path)

    wd = Watchdog()
    wd.heartbeat()
    # Simulate a stall by not heart-beating and checking with an injected clock.
    dumps = []
    monkeypatch.setattr(hang_dump, "dump_now",
                        lambda reason, directory=None: dumps.append(reason) or tmp_path / "x.txt")
    wd._state = _state(stall_threshold_s=0.05, cooldown_s=10.0, severe_threshold_s=10.0)
    wd._last_heartbeat = time.monotonic() - 1.0  # pretend heartbeat is 1s stale
    wd._check_once()
    assert dumps == ["stall"]


def test_watchdog_detects_a_blocked_qt_event_loop(qtbot, tmp_path, monkeypatch):
    """End-to-end: a real QTimer heartbeat on the (test) main thread, a real
    background checker thread, and a genuinely blocked event loop (a plain
    time.sleep on this thread -- the timer simply can't fire during it)."""
    from SciQLop.components.profiling import hang_dump
    from SciQLop.components.profiling.watchdog import start_qt_heartbeat

    dumps = []
    monkeypatch.setattr(
        hang_dump, "dump_now",
        lambda reason, directory=None: dumps.append(reason) or (tmp_path / "x.txt"))

    wd = Watchdog()
    wd._state = _state(stall_threshold_s=0.15, severe_threshold_s=100.0,
                       cooldown_s=100.0, max_dumps=5)
    wd._check_interval_s = 0.05
    timer = start_qt_heartbeat(wd, interval_ms=20)
    wd._stop.clear()
    wd._thread = threading.Thread(target=wd._run, name="test-watchdog", daemon=True)
    wd._thread.start()
    try:
        qtbot.wait(60)              # let a few real heartbeats land
        time.sleep(0.6)             # block the event loop -- heartbeat goes stale
        qtbot.wait(60)              # resume pumping
        assert "stall" in dumps
    finally:
        wd.stop()
        timer.stop()
