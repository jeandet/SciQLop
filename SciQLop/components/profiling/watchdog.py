"""GUI responsiveness watchdog.

Nothing previously noticed when SciQLop's main thread stalled, or captured
anything when it did -- every diagnostic in this package (hang_dump,
sampler, thread_cpu_top) is a tool someone has to remember to reach for
*during* the stall. This closes that gap: a heartbeat on the main thread,
checked from an independent thread, triggers an automatic dump the moment
a stall crosses a threshold.

The resampler thread pool and the remote worker are both already off the
main thread by design, so a multi-second main-thread stall is already
anomalous by the app's own architecture -- not a normal "big fetch" case.
Thresholds are
still `ProfilingSettings` fields, not hardcoded, since they're first-
principles estimates rather than measured against real-world false
positives/negatives.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import AbstractContextManager
from typing import Optional, Tuple

from . import hang_dump
from . import sampler as sampler_module
from .settings import ProfilingSettings

log = logging.getLogger(__name__)


class WatchdogState:
    """Pure trip-decision state machine: given (now, last_heartbeat), decide
    whether to dump silently, dump *and* surface, or do nothing. No I/O, no
    threading -- the whole point is to be trivially unit-testable with an
    injected clock."""

    def __init__(self, *, stall_threshold_s: float, severe_threshold_s: float,
                cooldown_s: float, max_dumps: int):
        self._stall_threshold_s = stall_threshold_s
        self._severe_threshold_s = severe_threshold_s
        self._cooldown_s = cooldown_s
        self._max_dumps = max_dumps
        self._stalled_since: Optional[float] = None
        self._last_dump_at: Optional[float] = None
        self._severe_dumped = False
        self._total_dumps = 0

    def check(self, now: float, last_heartbeat: float) -> Tuple[str, float]:
        """Returns (action, info). action is one of:
          "none"    -- nothing to do; info is the current elapsed stall time.
          "silent"  -- dump, don't surface; info is elapsed stall time.
          "surface" -- dump AND surface (severe); info is elapsed stall time.
          "cleared" -- heartbeat resumed; info is the total stall duration.
        """
        elapsed = now - last_heartbeat
        if elapsed < self._stall_threshold_s:
            if self._stalled_since is not None:
                duration = now - self._stalled_since
                self._stalled_since = None
                self._severe_dumped = False
                return "cleared", duration
            return "none", 0.0

        if self._stalled_since is None:
            self._stalled_since = now - elapsed
        if self._total_dumps >= self._max_dumps:
            return "none", elapsed
        if elapsed >= self._severe_threshold_s and not self._severe_dumped:
            self._severe_dumped = True
            self._last_dump_at = now
            self._total_dumps += 1
            return "surface", elapsed
        if self._last_dump_at is None or (now - self._last_dump_at) >= self._cooldown_s:
            self._last_dump_at = now
            self._total_dumps += 1
            return "silent", elapsed
        return "none", elapsed


class _Suppression(AbstractContextManager):
    """Reentrant suppression flag for known-legitimately-blocking call sites
    (a modal QFileDialog.exec(), a blocking startup migration) where the
    main thread is inside a nested event loop, not actually hung. A simple
    counter, deliberately not an auto-classifier -- callers opt in."""

    def __init__(self):
        self._depth = 0
        self._lock = threading.Lock()

    def __enter__(self) -> "_Suppression":
        with self._lock:
            self._depth += 1
        return self

    def __exit__(self, *exc) -> None:
        with self._lock:
            self._depth -= 1

    @property
    def active(self) -> bool:
        with self._lock:
            return self._depth > 0


_suppression = _Suppression()


def suppressed() -> _Suppression:
    return _suppression


class Watchdog:
    def __init__(self):
        self._last_heartbeat = time.monotonic()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._state: Optional[WatchdogState] = None
        self._check_interval_s = 1.0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def heartbeat(self) -> None:
        with self._lock:
            self._last_heartbeat = time.monotonic()

    def start(self) -> None:
        settings = ProfilingSettings()
        if not settings.watchdog_enabled or self.running:
            return
        self._state = WatchdogState(
            stall_threshold_s=settings.watchdog_stall_threshold_s,
            severe_threshold_s=settings.watchdog_severe_threshold_s,
            cooldown_s=settings.watchdog_cooldown_s,
            max_dumps=settings.watchdog_max_dumps_per_session,
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sciqlop-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._check_interval_s * 2 + 1)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._check_once()
            self._stop.wait(self._check_interval_s)

    def _check_once(self) -> None:
        if _suppression.active or self._state is None:
            return
        now = time.monotonic()
        with self._lock:
            last = self._last_heartbeat
        action, info = self._state.check(now, last)
        if action == "cleared":
            log.info("watchdog: stall cleared after %.1fs", info)
            return
        if action not in ("silent", "surface"):
            return
        path = hang_dump.dump_now("stall")
        sampler = sampler_module.get_sampler()
        if sampler.snapshot():
            sampler_module.flush_to_file(sampler, None, "stall")
        if action == "surface":
            log.error("watchdog: SEVERE stall (%.1fs, main thread unresponsive) -- dumped to %s",
                      info, path)
        else:
            log.warning("watchdog: main thread unresponsive for %.1fs -- dumped to %s",
                        info, path)


def start_qt_heartbeat(watchdog: "Watchdog", interval_ms: int = 200):
    """QTimer on the CURRENT (must be the main/GUI) thread that beats
    `watchdog`. A blocked event loop simply stops firing this timer, which
    is the whole mechanism -- the watchdog's own checker thread notices the
    silence. Returns the QTimer; caller must keep a reference alive."""
    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.setInterval(interval_ms)
    timer.timeout.connect(watchdog.heartbeat)
    timer.start()
    return timer
